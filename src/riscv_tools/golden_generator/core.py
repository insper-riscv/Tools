"""Generate a golden reference by running a test's ELF under Spike.

When the program writes its HTIF "done" value to tohost, Spike exits
and writes the memory range between the `begin_signature` and
`end_signature` symbols to a signature file, one 32-bit word per line.
Those symbols are added to a temporary copy of the ELF, so the
project's link script needs nothing extra. The golden is whatever the
program left in the range, whether it signalled pass or fail.
"""

import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from riscv_tools.spike_exec import (
    SpikeTarget,
    prepared_elf,
    require_spike,
    run_spike,
    spike_command,
    symbol_address,
)

# `nm -S` prints 4 whitespace-separated fields per sized symbol line:
# address, size, type, name.
_NM_SIZED_LINE_FIELDS = 4
_WORD_BYTES = 4
_BYTE_MASK = 0xFF


def symbol_range(nm_bin: str, elf_path: Path, symbol: str) -> tuple[int, int]:
    """Resolve a data symbol's [start, end) byte range from an ELF.

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
        [nm_bin, "-S", str(elf_path)],
        check=True,
        capture_output=True,
        text=True,
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


def generate_golden(
    target: SpikeTarget,
    elf_path: Path,
    addr_range: tuple[int, int],
    ram_base: int = 0,
    timeout_s: float = 60.0,
) -> dict[int, int]:
    """Run elf_path under Spike and snapshot a byte range of RAM.

    Snapshots the moment the program signals HTIF completion via tohost.

    Parameters
    ----------
    target : SpikeTarget
        The Spike run settings: binaries, `--isa=` value, memory regions
        (every region of real memory, passed as Spike's `-m`) and the
        tohost and entry symbols.
    elf_path : Path
        Path to the compiled test ELF to run.
    addr_range : tuple of (int, int)
        The (start, end) byte addresses to snapshot. `start` is
        inclusive and `end` exclusive; both are ABSOLUTE ELF/Spike
        addresses (e.g. straight from `nm`), not RAM-relative. The
        range is rounded up to whole 32-bit words, so a 1-byte symbol
        yields the 4 bytes of its word.
    ram_base : int, optional
        RAM's base byte address (memory.ram_base). It is subtracted from
        every address, so the golden keys are RAM-relative. Default 0.
    timeout_s : float, optional
        Seconds to wait for the program to signal completion.

    Returns
    -------
    dict of {int: int}
        A {byte_address: byte_value} dict covering every address in
        [start, end), RAM-relative (see ram_base), in the
        same shape mem_validator.compare's golden JSON expects (see
        write_golden_json).

    Raises
    ------
    RuntimeError
        Spike didn't write a signature (the program never signalled
        completion within timeout_s, or Spike failed), or the signature
        has an unexpected size.
    """
    addr_start, addr_end = addr_range
    word_count = -(-(addr_end - addr_start) // _WORD_BYTES)
    signature_end = addr_start + word_count * _WORD_BYTES

    words = _signature_words(
        replace(target, spike_bin=require_spike(target.spike_bin)),
        elf_path,
        {"begin_signature": addr_start, "end_signature": signature_end},
        timeout_s,
    )
    if len(words) != word_count:
        raise RuntimeError(
            f"expected {word_count} signature word(s) for {elf_path}, "
            f"got {len(words)}"
        )

    out: dict[int, int] = {}
    for index, word in enumerate(words):
        base = addr_start + index * _WORD_BYTES - ram_base
        for i in range(_WORD_BYTES):
            out[base + i] = (word >> (8 * i)) & _BYTE_MASK
    return out


def _signature_words(
    spike: SpikeTarget,
    elf_path: Path,
    signature_symbols: dict[str, int],
    timeout_s: float,
) -> list[int]:
    """Run elf_path under Spike and read the signature it writes.

    Parameters
    ----------
    spike : SpikeTarget
        The run settings, with `spike_bin` already resolved.
    elf_path : Path
        The compiled test ELF.
    signature_symbols : dict of {str: int}
        The `begin_signature` and `end_signature` addresses to add to
        the ELF's symbols.
    timeout_s : float
        Seconds to wait for the program to signal completion.

    Returns
    -------
    list of int
        The 32-bit words of the signature.

    Raises
    ------
    RuntimeError
        Spike timed out or wrote no signature.
    """
    entry_pc = symbol_address(spike.nm_bin, elf_path, spike.entry_symbol)
    with (
        tempfile.TemporaryDirectory(prefix="riscv-tools-golden-") as tmp,
        prepared_elf(
            spike.objcopy_bin,
            spike.nm_bin,
            elf_path,
            spike.tohost_symbol,
            signature_symbols,
        ) as elf,
    ):
        signature = Path(tmp) / "signature.txt"
        cmd = spike_command(
            spike,
            entry_pc,
            elf,
            (
                f"+signature={signature}",
                f"+signature-granularity={_WORD_BYTES}",
            ),
        )
        try:
            proc = run_spike(cmd, timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{elf_path} did not write {spike.tohost_symbol} "
                f"within {timeout_s}s"
            ) from exc
        if not signature.is_file():
            raise RuntimeError(
                f"spike wrote no signature for {elf_path} "
                f"(exit {proc.returncode}):\n{proc.stdout}{proc.stderr}"
            )
        return [int(line, 16) for line in signature.read_text().split()]


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
    payload = {
        f"0x{addr:08X}": value for addr, value in sorted(golden.items())
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
