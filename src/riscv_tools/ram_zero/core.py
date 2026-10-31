"""Clear every word of a RAM instance over JTAG."""

import tempfile
from pathlib import Path

from riscv_tools import mem_edit, ram_target, sdram_debug
from riscv_tools.bin_to_image import mif_text
from riscv_tools.jtag import JtagLink


def _blank_mif(depth: int) -> Path:
    """Build a full-depth all-zero .mif.

    mem_edit.write_full always overwrites the whole instance, so
    "zero it" just means "write this" rather than needing a dedicated
    zeroing primitive on the Quartus side.

    Parameters
    ----------
    depth : int
        Word depth of the target memory instance; the .mif covers
        addresses [0, depth), all zero.

    Returns
    -------
    Path
        Path to a newly created temp file holding the .mif content.
        Caller is responsible for deleting it.
    """
    text = mif_text(depth, [f"    [0000..{depth - 1:04X}] : 00000000;"])
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mif", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
    return Path(f.name)


def zero_ram(
    link: JtagLink, ram_mem_instance: ram_target.RamTarget, ram_words: int
) -> None:
    """Clear every word of RAM over JTAG, without reprogramming.

    Useful between runs when the program's own restart path does not
    clear the RAM, such as a memory test that compares all of it.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached: an instance index, or SdramDebugRam for
        the SDRAM.
    ram_words : int
        Word depth of the RAM; every word in [0, ram_words) is cleared.

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
