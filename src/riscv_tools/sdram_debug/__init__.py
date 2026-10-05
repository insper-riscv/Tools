"""Read and write the SDRAM through its JTAG debug port."""

from .core import fill, read_words, write_word

__all__ = ["fill", "read_words", "write_word"]
