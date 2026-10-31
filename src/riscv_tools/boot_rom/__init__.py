"""Builds the fixed, shared bootloader (boot_rom.S) once per run."""

from .core import build_boot_rom

__all__ = ["build_boot_rom"]
