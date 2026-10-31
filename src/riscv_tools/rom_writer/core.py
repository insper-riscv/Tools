"""Load a new ROM image into an already-programmed board over JTAG."""

from collections.abc import Sequence
from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def write_rom(
    link: JtagLink, rom_mem_instances: Sequence[int], mif_path: Path
) -> None:
    """Load a new ROM image into an already-programmed board over JTAG.

    Pairs with htif.pulse_fromhost to make the core jump back to
    _start and run it (see crt0.S in the consuming project).

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    rom_mem_instances : sequence of int
        In-System Memory Content Editor instance indices of the ROM
        (quartus.rom_mem_instances). Every instance gets the same
        content, in order, so a ROM duplicated into several BRAMs stays
        in sync.
    mif_path : Path
        Path to the .mif whose content replaces each ROM instance's
        entire depth.

    Returns
    -------
    None
    """
    mem_edit.write_full_multi(link, rom_mem_instances, mif_path)
