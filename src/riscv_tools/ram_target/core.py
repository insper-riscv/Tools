"""Where a project's RAM lives, and how the host reaches it over JTAG.

Two kinds of RAM exist. A RAM inside the FPGA is a memory instance of the
In-System Memory Content Editor, named by its instance index (an int). A RAM
outside the FPGA, the SDRAM of the SDRAM platform, is reached through the SDRAM
debug port (SdramDebugRam). The modules that read the mailbox, set the go flag,
dump or zero the RAM take a RamTarget and call these functions, so they work
with either.

Word offsets are counted from the base of the RAM (memory.ram_base). For the
SDRAM that base is the base of the SDRAM, so a word offset is also a word
address of the debug port.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools import mem_edit, sdram_debug
from riscv_tools.jtag import JtagLink


@dataclass(frozen=True)
class SdramDebugRam:
    """The RAM is the SDRAM, reached through its JTAG debug port."""


RamTarget = int | SdramDebugRam


def target_from_config(cfg: dict[str, Any]) -> RamTarget:
    """Pick how to reach the RAM from a project's merged config.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: quartus.ram_backend is "ismce" (the default: a memory
        instance of the FPGA, quartus.ram_mem_instance) or "sdram_debug".

    Returns
    -------
    int or SdramDebugRam
        The ISMCE instance index of the RAM, or SdramDebugRam.

    Raises
    ------
    ValueError
        quartus.ram_backend is not one of the two backends.
    """
    quartus = cfg["quartus"]
    backend = quartus.get("ram_backend", "ismce")
    if backend == "sdram_debug":
        return SdramDebugRam()
    if backend == "ismce":
        return int(quartus["ram_mem_instance"])
    raise ValueError(
        f"quartus.ram_backend must be 'ismce' or 'sdram_debug', not {backend!r}"
    )


def read_words(
    link: JtagLink, target: RamTarget, word_offset: int, word_count: int = 1
) -> list[int]:
    """Read contiguous words of the RAM.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    target : int or SdramDebugRam
        How the RAM is reached (see RamTarget).
    word_offset : int
        Word offset from the base of the RAM of the first word.
    word_count : int, optional
        How many contiguous words to read. Defaults to 1.

    Returns
    -------
    list of int
        The values read, in address order.
    """
    if isinstance(target, SdramDebugRam):
        return sdram_debug.read_words(link, word_offset, word_count)
    return mem_edit.read_words(link, target, word_offset, word_count)


def write_word(link: JtagLink, target: RamTarget, word_offset: int, value: int) -> None:
    """Write one word of the RAM.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    target : int or SdramDebugRam
        How the RAM is reached (see RamTarget).
    word_offset : int
        Word offset from the base of the RAM.
    value : int
        32-bit unsigned value to write.

    Returns
    -------
    None
    """
    if isinstance(target, SdramDebugRam):
        sdram_debug.write_word(link, word_offset, value)
    else:
        mem_edit.write_word(link, target, word_offset, value)


def sparse_mif_words(
    link: JtagLink, target: RamTarget, words: Sequence[int], out_mif: Path
) -> None:
    """Save only the given words of the RAM to a .mif (the rest is left out).

    A RAM of 64 MB cannot be dumped whole over JTAG, and a golden checks a few
    words. The file has one line per word, which mem_validator reads like any
    other dump.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    target : int or SdramDebugRam
        How the RAM is reached (see RamTarget).
    words : sequence of int
        Word offsets to save (any order, repeats allowed).
    out_mif : Path
        Path to write the .mif to (overwritten if it already exists).

    Returns
    -------
    None
    """
    ordered = sorted(set(words))
    values: dict[int, int] = {}
    start = 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        run = ordered[start : end + 1]
        values |= dict(
            zip(run, read_words(link, target, run[0], len(run)), strict=True)
        )
        start = end + 1
    lines = [
        "WIDTH=32;",
        f"DEPTH={len(ordered)};",
        "ADDRESS_RADIX=HEX;",
        "DATA_RADIX=HEX;",
        "CONTENT BEGIN",
        *[f"  {offset:X} : {value:08X};" for offset, value in sorted(values.items())],
        "END;",
    ]
    out_mif.write_text("\n".join(lines) + "\n")
