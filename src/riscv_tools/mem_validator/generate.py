"""Generates a golden reference by running a test's ELF under Spike
(vendor/riscv-isa-sim) and snapshotting RAM once it reaches
restart_symbol (crt0.S:rv32_wait_restart in the consuming project) —
the same point RV32_PASS/RV32_FAIL leave the core in on real hardware.

Uses Spike's interactive debug console (`-d`), not its normal
run-to-completion/HTIF exit path: our bare-metal test programs use a
custom mailbox/restart protocol, not the tohost/fromhost convention
Spike's ordinary exit handling expects, so a breakpoint on a known
symbol is what tells Spike when the program is "done".

NOTE: spike's `-d` command syntax below (`until pc 0 <addr>`,
`mem 0 <addr>`, `q`) matches Spike's long-documented interactive
debugger, but hasn't been exercised against a built vendor/riscv-isa-sim
on this workstation yet — verify against a real build before trusting
generated goldens.
"""
import json
import re
import subprocess
from pathlib import Path

MEM_REPLY_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def _symbol_address(nm_bin: str, elf_path: Path, symbol: str) -> int:
    """Resolves a symbol's address from an ELF's symbol table.

    Args:
        nm_bin: `nm` binary name/path for the target toolchain (e.g.
            "riscv32-unknown-elf-nm").
        elf_path: Path to the ELF to inspect.
        symbol: Symbol name to look up (e.g. "rv32_wait_restart").

    Returns:
        The symbol's address.

    Raises:
        RuntimeError: symbol isn't present in elf_path's symbol table.
    """
    out = subprocess.run([nm_bin, str(elf_path)], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == symbol:
            return int(parts[0], 16)
    raise RuntimeError(f"symbol {symbol!r} not found in {elf_path}")


def _read_words_at_stop(spike_bin: str, isa: str, elf_path: Path, stop_pc: int, word_addrs: list[int]) -> list[int]:
    """Runs elf_path under Spike's interactive debugger, halts once PC
    reaches stop_pc, then reads a list of memory words.

    Args:
        spike_bin: `spike` binary name/path (built from
            vendor/riscv-isa-sim).
        isa: `--isa=` value to run Spike with (e.g. "rv32im").
        elf_path: Path to the ELF to execute.
        stop_pc: Program counter value to run until, before reading
            any memory (see _symbol_address).
        word_addrs: Byte addresses (each must be word-aligned) to read
            one 32-bit word from, in order.

    Returns:
        One value per entry in word_addrs, in the same order.

    Raises:
        RuntimeError: Spike's output didn't contain exactly
            len(word_addrs) "mem" replies (e.g. a crashed/misbehaving
            run).
        subprocess.CalledProcessError: spike_bin exited non-zero.
    """
    commands = [f"until pc 0 {stop_pc:x}"]
    commands += [f"mem 0 {addr:x}" for addr in word_addrs]
    commands.append("q")

    proc = subprocess.run(
        [spike_bin, f"--isa={isa}", "-d", str(elf_path)],
        input="\n".join(commands) + "\n",
        check=True, capture_output=True, text=True,
    )
    values = [int(line.strip(), 16) for line in proc.stdout.splitlines() if MEM_REPLY_RE.match(line.strip())]
    if len(values) != len(word_addrs):
        raise RuntimeError(
            f"expected {len(word_addrs)} 'mem' replies from spike, got {len(values)}:\n{proc.stdout}"
        )
    return values


def generate_golden(
    spike_bin: str,
    nm_bin: str,
    elf_path: Path,
    isa: str,
    restart_symbol: str,
    addr_start: int,
    addr_end: int,
) -> dict[int, int]:
    """Runs elf_path under Spike and snapshots a byte range of RAM at
    the moment it reaches restart_symbol.

    Args:
        spike_bin: `spike` binary name/path (built from
            vendor/riscv-isa-sim).
        nm_bin: `nm` binary name/path for the target toolchain, used
            to resolve restart_symbol's address.
        elf_path: Path to the compiled test ELF to run.
        isa: `--isa=` value to run Spike with (e.g. "rv32im") —
            should match the test's own march.
        restart_symbol: Symbol name Spike halts at before reading
            memory (default "rv32_wait_restart" — see
            mem_validator.__config__.DEFAULTS).
        addr_start: First byte address to snapshot (inclusive).
        addr_end: One past the last byte address to snapshot
            (exclusive) — addr_end - addr_start must be a multiple of
            4.

    Returns:
        A {byte_address: byte_value} dict covering every address in
        [addr_start, addr_end), in the same shape
        mem_validator.compare's golden JSON expects (see
        write_golden_json).
    """
    stop_pc = _symbol_address(nm_bin, elf_path, restart_symbol)
    word_addrs = list(range(addr_start, addr_end, 4))
    words = _read_words_at_stop(spike_bin, isa, elf_path, stop_pc, word_addrs)

    out = {}
    for waddr, wval in zip(word_addrs, words):
        for i in range(4):
            out[waddr + i] = (wval >> (8 * i)) & 0xFF
    return out


def write_golden_json(golden: dict[int, int], out_path: Path) -> None:
    """Writes a byte map to a golden JSON file, in the format
    mem_validator.compare expects.

    Args:
        golden: A {byte_address: byte_value} dict, e.g. from
            generate_golden.
        out_path: Path to write the JSON to (overwritten if it
            already exists). Keys are written as sorted, zero-padded
            8-digit hex strings ("0xNNNNNNNN").

    Returns:
        None.
    """
    payload = {f"0x{addr:08X}": value for addr, value in sorted(golden.items())}
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
