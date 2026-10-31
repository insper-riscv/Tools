"""JTAG-dumps the whole RAM instance to a .mif."""

from riscv_tools.ram_dump.core import dump_ram

__all__ = ["dump_ram"]
