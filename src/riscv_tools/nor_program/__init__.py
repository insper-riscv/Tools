"""Write a bank of the NOR chip of a board with no FLASH loader."""

from riscv_tools.nor_program.core import (
    JOB_MAGIC,
    RAM_BOOT_MAGIC,
    Layout,
    build_programmer,
    layout_of,
    load_bank_image,
    program_bank,
)

__all__ = [
    "JOB_MAGIC",
    "RAM_BOOT_MAGIC",
    "Layout",
    "build_programmer",
    "layout_of",
    "load_bank_image",
    "program_bank",
]
