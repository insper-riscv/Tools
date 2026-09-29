"""Builds the fixed, shared bootloader (boot_rom.S), once, reused by every test."""

from .core import build_boot_rom

__all__ = ["build_boot_rom"]
