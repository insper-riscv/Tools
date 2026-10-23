"""Save a RAM's content to a .mif over JTAG."""

from collections.abc import Sequence
from pathlib import Path

from riscv_tools import mem_edit, ram_target
from riscv_tools.jtag import JtagLink


def dump_ram(
    link: JtagLink,
    ram_mem_instance: ram_target.RamTarget,
    out_mif: Path,
    words: Sequence[int] | None = None,
) -> None:
    """Save the RAM content to a .mif over JTAG.

    Used for memory tests, where the PASS/FAIL mailbox alone isn't
    enough. A RAM inside the FPGA is saved whole (words is not needed). A RAM in
    the SDRAM is too big to read whole over JTAG, so only the given words are
    saved.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached: the In-System Memory Content Editor instance
        index of the RAM, or SdramDebugRam for a RAM in the SDRAM (see
        ram_target).
    out_mif : Path
        Path to write the .mif to (overwritten if it already exists).
    words : sequence of int, optional
        Word offsets from the base of the RAM to save. Required for
        SdramDebugRam, ignored for a memory instance of the FPGA.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        The RAM is in the SDRAM and no words were given.
    """
    if isinstance(ram_mem_instance, ram_target.SdramDebugRam):
        if words is None:
            raise ValueError(
                "the RAM is the SDRAM: it is too big to dump whole, "
                "give the words to save"
            )
        ram_target.sparse_mif_words(link, ram_mem_instance, words, out_mif)
        return
    mem_edit.dump(link, ram_mem_instance, out_mif)
