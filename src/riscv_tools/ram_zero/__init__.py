"""JTAG-zeroes the whole RAM instance without reprogramming."""

from riscv_tools.ram_zero.core import zero_ram

__all__ = ["zero_ram"]
