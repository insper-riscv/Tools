from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def dump_ram(link: JtagLink, ram_mem_instance: int, out_mif: Path) -> None:
    """Saves the whole RAM content to a .mif over JTAG — used for
    RV32_TEST_KIND: integration tests, where the PASS/FAIL mailbox
    alone isn't enough (see riscv_tools.mem_validator.compare)."""
    mem_edit.dump(link, ram_mem_instance, out_mif)
