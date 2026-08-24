"""Generate a golden reference by running a test's ELF under Spike.

Uses vendor/riscv-isa-sim and snapshots RAM once the program writes
its HTIF "done" signal to tohost (see link.ld/crt0.S in the consuming
project) — the standard convention Spike/riscv-tests use, rather than
a project-specific address like crt0.S's rv32_wait_restart symbol.
Decoupled from crt0.S's internals: as long as the consuming project's
crt0.S writes tohost on completion (it does, translating the mailbox
PASS/FAIL into tohost's 1/3 encoding — see crt0.S), this works
regardless of how rv32_wait_restart or anything else in crt0.S is laid
out or renamed.

Uses Spike's interactive debug console (`-d`), not its normal
run-to-completion/HTIF exit path: run-to-completion mode EXITS the
process the moment tohost is written, which would take the simulated
memory down with it before we get a chance to read the RAM range we
actually want. Scripting the debug console instead lets us stop at
that same moment without losing access to memory afterward.

Commands are fed via `--debug-cmd=<file>`, NOT piped to stdin: the
console's own readline() is written for an interactive TTY (raw
termios mode, arrow-key/history handling) and does not reliably detect
EOF on a piped, non-TTY stdin — verified empirically (against a real
build of vendor/riscv-isa-sim) that piping commands over stdin makes
Spike single-step forever after running out of input instead of
exiting, even after a `q`. `--debug-cmd` reads commands from a real
file via a plain fscanf loop instead, sidestepping readline()
entirely. Also verified: `mem`/`while mem` take a bare address with NO
core argument for physical addressing (a `[core]` argument, if given,
treats the address as VIRTUAL instead — see interactive.cc's own
`while mem [core] <addr> <val>` usage line).
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

MEM_REPLY_RE = re.compile(r"^0x[0-9a-fA-F]+$")
# Spike's interactive console caps each command line at 40 chars
# (MAX_CMD_STR in interactive.cc) — a hard ceiling on how much any one
# generated command line can hold.
MAX_CMD_LEN = 40
# `nm`'s default output has exactly 3 whitespace-separated fields per
# symbol line: address, type, name.
_NM_LINE_FIELDS = 3


def _symbol_address(nm_bin: str, elf_path: Path, symbol: str) -> int:
    """Resolve a symbol's address from an ELF's symbol table.

    Parameters
    ----------
    nm_bin : str
        `nm` binary name/path for the target toolchain (e.g.
        "riscv32-unknown-elf-nm").
    elf_path : Path
        Path to the ELF to inspect.
    symbol : str
        Symbol name to look up (e.g. "rv32_wait_restart").

    Returns
    -------
    int
        The symbol's address.

    Raises
    ------
    RuntimeError
        symbol isn't present in elf_path's symbol table.
    """
    out = subprocess.run(
        [nm_bin, str(elf_path)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == _NM_LINE_FIELDS and parts[2] == symbol:
            return int(parts[0], 16)
    raise RuntimeError(f"symbol {symbol!r} not found in {elf_path}")


def _read_words_after_tohost(
    spike_bin: str, isa: str, elf_path: Path, tohost_addr: int, word_addrs: list[int]
) -> list[int]:
    """Run elf_path under Spike's interactive debugger and read memory words.

    Halts the instant tohost_addr's word becomes nonzero (the
    program's HTIF "done" signal — see crt0.S), then reads a list of
    memory words.

    Parameters
    ----------
    spike_bin : str
        `spike` binary name/path (built from vendor/riscv-isa-sim).
    isa : str
        `--isa=` value to run Spike with (e.g. "rv32im").
    elf_path : Path
        Path to the ELF to execute.
    tohost_addr : int
        Byte address of the `tohost` symbol (see _symbol_address) —
        watched via Spike's `while mem ... 0` rather than `until mem
        ... <value>` specifically because we don't know in advance
        whether the test will write 1 (pass) or 3 (fail); `while`
        stops on ANY change away from 0, `until` would need the exact
        value.
    word_addrs : list of int
        Byte addresses (each must be word-aligned) to read one 32-bit
        word from, in order.

    Returns
    -------
    list of int
        One value per entry in word_addrs, in the same order.

    Raises
    ------
    RuntimeError
        A generated command line exceeds Spike's MAX_CMD_LEN, or
        Spike's output didn't contain exactly len(word_addrs) "mem"
        replies (e.g. a crashed/misbehaving run).
    subprocess.CalledProcessError
        spike_bin exited non-zero.
    """
    commands = [f"while mem {tohost_addr:x} 0"]
    commands += [f"mem {addr:x}" for addr in word_addrs]
    commands.append("q")

    too_long = [c for c in commands if len(c) > MAX_CMD_LEN]
    if too_long:
        raise RuntimeError(
            f"command(s) exceed spike's {MAX_CMD_LEN}-char line limit: {too_long}"
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".spikecmd", delete=False) as f:
        f.write("\n".join(commands) + "\n")
        cmd_file = Path(f.name)

    try:
        proc = subprocess.run(
            [spike_bin, f"--isa={isa}", "-d", f"--debug-cmd={cmd_file}", str(elf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        cmd_file.unlink(missing_ok=True)

    # Spike sends its own command replies to stderr, not stdout, for
    # the whole duration --debug-cmd is supplying commands (see
    # interactive.cc: "while we get input from file, output goes to
    # stderr") — confirmed empirically against a real build; stdout
    # came back completely empty in the same run where stderr had the
    # "mem" reply.
    values = [
        int(line.strip(), 16)
        for line in proc.stderr.splitlines()
        if MEM_REPLY_RE.match(line.strip())
    ]
    if len(values) != len(word_addrs):
        raise RuntimeError(
            f"expected {len(word_addrs)} 'mem' replies from spike, "
            f"got {len(values)}:\n{proc.stderr}"
        )
    return values


# Each arg is an independent Spike run setting — not bundleable
# without a config object this module doesn't otherwise need.
def generate_golden(  # noqa: PLR0913, PLR0917
    spike_bin: str,
    nm_bin: str,
    elf_path: Path,
    isa: str,
    tohost_symbol: str,
    addr_start: int,
    addr_end: int,
) -> dict[int, int]:
    """Run elf_path under Spike and snapshot a byte range of RAM.

    Snapshots the moment it signals HTIF completion via tohost.

    Parameters
    ----------
    spike_bin : str
        `spike` binary name/path (built from vendor/riscv-isa-sim).
    nm_bin : str
        `nm` binary name/path for the target toolchain, used to
        resolve tohost_symbol's address.
    elf_path : Path
        Path to the compiled test ELF to run.
    isa : str
        `--isa=` value to run Spike with (e.g. "rv32im") — should
        match the test's own march.
    tohost_symbol : str
        Symbol name Spike watches for a nonzero write before reading
        memory (default "tohost" — see
        golden_generator.__config__.DEFAULTS). The consuming project's
        crt0.S/link.ld must define this symbol and write to it on
        completion.
    addr_start : int
        First byte address to snapshot (inclusive).
    addr_end : int
        One past the last byte address to snapshot (exclusive) —
        addr_end - addr_start must be a multiple of 4.

    Returns
    -------
    dict of {int: int}
        A {byte_address: byte_value} dict covering every address in
        [addr_start, addr_end), in the same shape
        mem_validator.compare's golden JSON expects (see
        write_golden_json).
    """
    tohost_addr = _symbol_address(nm_bin, elf_path, tohost_symbol)
    word_addrs = list(range(addr_start, addr_end, 4))
    words = _read_words_after_tohost(spike_bin, isa, elf_path, tohost_addr, word_addrs)

    out: dict[int, int] = {}
    for waddr, wval in zip(word_addrs, words, strict=True):
        for i in range(4):
            out[waddr + i] = (wval >> (8 * i)) & 0xFF
    return out


def write_golden_json(golden: dict[int, int], out_path: Path) -> None:
    """Write a byte map to a golden JSON file.

    Uses the format mem_validator.compare expects.

    Parameters
    ----------
    golden : dict of {int: int}
        A {byte_address: byte_value} dict, e.g. from generate_golden.
    out_path : Path
        Path to write the JSON to (overwritten if it already exists).
        Keys are written as sorted, zero-padded 8-digit hex strings
        ("0xNNNNNNNN").

    Returns
    -------
    None
    """
    payload = {f"0x{addr:08X}": value for addr, value in sorted(golden.items())}
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
