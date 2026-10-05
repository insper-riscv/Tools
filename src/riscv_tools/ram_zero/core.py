"""Clear every word of a RAM instance over JTAG, without reprogramming."""

import tempfile
from pathlib import Path

from riscv_tools import mem_edit, ram_target, sdram_debug
from riscv_tools.jtag import JtagLink


def _blank_mif(depth: int) -> Path:
    """Build a full-depth all-zero .mif.

    mem_edit.write_full always overwrites the whole instance, so
    "zero it" just means "write this" rather than needing a dedicated
    zeroing primitive on the Quartus side.

    Parameters
    ----------
    depth : int
        Word depth of the target memory instance — the .mif covers
        addresses [0, depth), all zero.

    Returns
    -------
    Path
        Path to a newly created temp file holding the .mif content.
        Caller is responsible for deleting it.
    """
    lines = [
        "WIDTH=32;",
        f"DEPTH={depth};",
        "",
        "ADDRESS_RADIX=HEX;",
        "DATA_RADIX=HEX;",
        "",
        "CONTENT BEGIN",
        f"    [0000..{depth - 1:04X}] : 00000000;",
        "END;",
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mif", delete=False) as f:
        f.write("\n".join(lines) + "\n")
    return Path(f.name)


def zero_ram(
    link: JtagLink, ram_mem_instance: ram_target.RamTarget, ram_words: int
) -> None:
    """Clear every word of RAM over JTAG, without reprogramming the FPGA.

    Useful between test runs when a program's own crt0 restart path
    (mailbox/go_flag self-clear) isn't enough — e.g. re-running a
    memory test that dumps and compares the whole RAM, where leftover
    words from a previous test would corrupt the comparison.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached: the In-System Memory Content Editor instance
        index of the RAM (quartus.ram_mem_instance in the project's
        config.yaml), or SdramDebugRam for a RAM in the SDRAM, which is filled
        by the board itself (no shift per word).
    ram_words : int
        Word depth of the RAM instance — every word in [0, ram_words)
        is cleared.

    Returns
    -------
    None
    """
    if isinstance(ram_mem_instance, ram_target.SdramDebugRam):
        sdram_debug.fill(link, 0, ram_words, 0)
        return
    blank = _blank_mif(ram_words)
    try:
        mem_edit.write_full(link, ram_mem_instance, blank)
    finally:
        blank.unlink(missing_ok=True)
