from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def write_rom(link: JtagLink, rom_mem_instance: int, mif_path: Path) -> None:
    """Loads a new ROM image into an already-programmed board over
    JTAG. Pairs with mailbox.pulse_go_flag to make the core jump 
    back to _start and run it (see crt0.S in the consuming
    project).

    Args:
        link: Which JTAG cable/chip to write to.
        rom_mem_instance: In-System Memory Content Editor instance
            index of the ROM (quartus.rom_mem_instance in the
            project's config.yaml).
        mif_path: Path to the .mif whose content replaces the ROM's
            entire depth.

    Returns:
        None.
    """
    mem_edit.write_full(link, rom_mem_instance, mif_path)
