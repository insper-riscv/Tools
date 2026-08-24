from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def dump_ram(link: JtagLink, ram_mem_instance: int, out_mif: Path) -> None:
    """Saves the whole RAM content to a .mif over JTAG, used for
    memory tests, where the PASS/FAIL mailbox alone isn't enough.

    Args:
        link: Which JTAG cable/chip to read from.
        ram_mem_instance: In-System Memory Content Editor instance
            index of the RAM.
        out_mif: Path to write the .mif to (overwritten if it already
            exists).

    Returns:
        None.
    """
    mem_edit.dump(link, ram_mem_instance, out_mif)
