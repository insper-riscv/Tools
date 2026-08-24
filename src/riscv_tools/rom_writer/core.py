from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def write_rom(link: JtagLink, rom_mem_instance: int, mif_path: Path) -> None:
    """Loads a new ROM image into an already-programmed board over
    JTAG — no recompile, no reprogram. Pairs with mailbox.pulse_go_flag
    to make the core jump back to _start and run it (see crt0.S in the
    consuming project)."""
    mem_edit.write_full(link, rom_mem_instance, mif_path)
