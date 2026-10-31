"""Builds the fixed, shared bootloader (boot_rom.S) once per run."""

from riscv_tools.boot_rom.core import build_boot_rom

__all__ = ["build_boot_rom"]
