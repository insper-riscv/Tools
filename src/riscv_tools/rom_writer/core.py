"""Load a new ROM image into an already-programmed board over JTAG."""

from collections.abc import Sequence
from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def write_rom(link: JtagLink, rom_mem_instances: Sequence[int], mif_path: Path) -> None:
    """Load a new ROM image into an already-programmed board over JTAG.

    Pairs with mailbox.pulse_go_flag to make the core jump back to
    _start and run it (see crt0.S in the consuming project).

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    rom_mem_instances : sequence of int
        In-System Memory Content Editor instance index/indices of the
        ROM (quartus.rom_mem_instances in the project's config.yaml) —
        a list rather than a single int because a Harvard-modificado
        project (see RV32IM) physically duplicates ROM into a second
        BRAM for its MEM-stage read port instead of using one true
        dual-port memory (Quartus's ENABLE_RUNTIME_MOD/In-System Memory
        Content Editor doesn't support DUAL_PORT operation_mode in the
        Lite edition — confirmed via a real quartus_map run). Every
        instance listed gets the exact same content, in order, so they
        never drift out of sync with each other.
    mif_path : Path
        Path to the .mif whose content replaces each ROM instance's
        entire depth.

    Returns
    -------
    None
    """
    mem_edit.write_full_multi(link, rom_mem_instances, mif_path)
