"""Read and write the SDRAM through its JTAG debug port."""

from riscv_tools.sdram_debug.core import (
    fill,
    load_words,
    read_words,
    write_word,
)

__all__ = ["fill", "load_words", "read_words", "write_word"]
