"""Generate a golden reference by running a test's ELF under Spike.

Spike runs the program to completion. When the program writes its HTIF
"done" value to tohost (see link.ld/crt0.S in the consuming project),
Spike exits and, because the ELF carries `begin_signature` and
`end_signature` symbols, writes that byte range of memory to a
signature file, one 32-bit word per line. Those two symbols are added
to a temporary copy of the ELF from the test's `results` symbol, so
the project's own link script needs nothing extra.

The golden is whatever the program left in the range, regardless of
whether it signalled pass or fail through tohost.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from riscv_tools.spike_exec import (
    prepared_elf,
    require_spike,
    spike_command,
    symbol_address,
)

# `nm -S` prints 4 whitespace-separated fields per sized symbol line:
# address, size, type, name.
_NM_SIZED_LINE_FIELDS = 4
_WORD_BYTES = 4


def symbol_range(nm_bin: str, elf_path: Path, symbol: str) -> tuple[int, int]:
    """Resolve a data symbol's [start, end) byte range from an ELF, via its size.

    Lets a test declare one C global (e.g. ``volatile unsigned int
    results[3];``) or one asm label with an explicit ``.size`` directive
    (plain labels don't get one for free; GNU as only emits `.size`
    automatically for compiler-generated symbols) as its "results"
    region, instead of a human counting bytes to pass --start/--end by
    hand. ``nm -S`` reports (address, size, type, name) for every
    symbol; a compiler emits accurate `.size` info for global data
    objects automatically.

    Parameters
    ----------
    nm_bin : str
        `nm` binary name/path for the target toolchain.
    elf_path : Path
        Path to the ELF to inspect.
    symbol : str
        Symbol name to look up (e.g. "results").

    Returns
    -------
    tuple of (int, int)
        (start, end) byte addresses; end is start + the symbol's
        size, exclusive, same shape generate_golden's addr_start/
        addr_end expect.

    Raises
    ------
    RuntimeError
        symbol isn't present in elf_path's symbol table, or has a
        recorded size of 0 (e.g. it's a code label, not a sized data
        object; `nm -S` only reports real sizes for the latter).
    """
    out = subprocess.run(
        [nm_bin, "-S", str(elf_path)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == _NM_SIZED_LINE_FIELDS and parts[3] == symbol:
            start, size = int(parts[0], 16), int(parts[1], 16)
            if size == 0:
                raise RuntimeError(
                    f"symbol {symbol!r} in {elf_path} has size 0; nm -S only "
                    "reports real sizes for sized data objects (e.g. a C "
                    "global, or an asm label with an explicit `.size` "
                    "directive), not plain code/branch labels"
                )
            return start, start + size
    raise RuntimeError(f"symbol {symbol!r} not found in {elf_path}")


# Each arg is an independent Spike run setting; not bundleable
# without a config object this module doesn't otherwise need.
def generate_golden(  # noqa: PLR0913, PLR0917
    spike_bin: str,
    nm_bin: str,
    elf_path: Path,
    isa: str,
    mem_regions: list[tuple[int, int]],
    tohost_symbol: str,
    addr_start: int,
    addr_end: int,
    ram_base: int = 0,
    entry_symbol: str = "_start",
    objcopy_bin: str = "riscv32-unknown-elf-objcopy",
    timeout_s: float = 60.0,
) -> dict[int, int]:
    """Run elf_path under Spike and snapshot a byte range of RAM.

    Snapshots the moment the program signals HTIF completion via tohost.

    Parameters
    ----------
    spike_bin : str
        `spike` binary name/path (see spike_exec.require_spike).
    nm_bin : str
        `nm` binary name/path for the target toolchain, used to
        resolve the entry and tohost symbols.
    elf_path : Path
        Path to the compiled test ELF to run.
    isa : str
        `--isa=` value to run Spike with (e.g. "rv32im"); should
        match the test's own march.
    mem_regions : list of (int, int)
        (base, size) byte pairs describing every region of real
        memory the target actually has, e.g. `[(0,
        memory.rom_words*4), (memory.ram_base,
        memory.ram_words*4)]`. Passed straight through as Spike's `-m`.
    tohost_symbol : str
        Symbol the program writes a nonzero value to on completion
        (default "tohost", see golden_generator.__config__.DEFAULTS).
        The consuming project's crt0.S/link.ld must define it.
    addr_start : int
        First byte address to snapshot (inclusive); an ABSOLUTE
        ELF/Spike address (e.g. straight from `nm`), not RAM-relative.
    addr_end : int
        One past the last byte address to snapshot (exclusive). The
        range is rounded up to whole 32-bit words, so a 1-byte symbol
        yields the 4 bytes of its word. Same absolute convention as
        addr_start.
    ram_base : int, optional
        RAM's base byte address (memory.ram_base in the project's
        config.yaml, 0 for a project where RAM starts at address 0).
        Subtracted from every address before it's used as a golden
        JSON key, so the output stays RAM-relative (word 0 = RAM's own
        first byte) regardless of where RAM is actually mapped,
        matching mem_validator.compare's dump_ram convention.
    entry_symbol : str, optional
        Symbol execution starts at ("_start", the usual crt0 entry
        label) unless a project names it something else.
    objcopy_bin : str, optional
        `objcopy` binary for the target toolchain, used to add the
        symbols Spike needs to a copy of the ELF.
    timeout_s : float, optional
        Seconds to wait for the program to signal completion.

    Returns
    -------
    dict of {int: int}
        A {byte_address: byte_value} dict covering every address in
        [addr_start, addr_end), RAM-relative (see ram_base), in the
        same shape mem_validator.compare's golden JSON expects (see
        write_golden_json).

    Raises
    ------
    RuntimeError
        Spike didn't write a signature (the program never signalled
        completion within timeout_s, or Spike failed), or the signature
        has an unexpected size.
    """
    word_count = -(-(addr_end - addr_start) // _WORD_BYTES)
    signature_end = addr_start + word_count * _WORD_BYTES

    spike = require_spike(spike_bin)
    entry_pc = symbol_address(nm_bin, elf_path, entry_symbol)
    signature_symbols = {"begin_signature": addr_start, "end_signature": signature_end}

    with (
        tempfile.TemporaryDirectory(prefix="riscv-tools-golden-") as tmp,
        prepared_elf(
            objcopy_bin, nm_bin, elf_path, tohost_symbol, signature_symbols
        ) as elf,
    ):
        signature = Path(tmp) / "signature.txt"
        cmd = spike_command(
            spike,
            isa,
            mem_regions,
            entry_pc,
            elf,
            (f"+signature={signature}", f"+signature-granularity={_WORD_BYTES}"),
        )
        try:
            proc = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{elf_path} did not write {tohost_symbol} within {timeout_s}s"
            ) from exc
        if not signature.is_file():
            raise RuntimeError(
                f"spike wrote no signature for {elf_path} "
                f"(exit {proc.returncode}):\n{proc.stdout}{proc.stderr}"
            )
        words = [int(line, 16) for line in signature.read_text().split()]

    if len(words) != word_count:
        raise RuntimeError(
            f"expected {word_count} signature word(s) for {elf_path}, got {len(words)}"
        )

    out: dict[int, int] = {}
    for index, word in enumerate(words):
        base = addr_start + index * _WORD_BYTES - ram_base
        for i in range(_WORD_BYTES):
            out[base + i] = (word >> (8 * i)) & 0xFF
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
