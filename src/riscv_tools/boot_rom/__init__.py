"""Builds the fixed, shared bootloader (boot_rom.S) once per run."""

from riscv_tools.boot_rom.core import BootRomOptions, build_boot_rom

__all__ = ["BootRomOptions", "build_boot_rom"]
