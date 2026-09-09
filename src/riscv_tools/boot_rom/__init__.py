"""Builds the fixed, shared bootloader (boot_rom.S) -- built once, reused across every test."""

from .core import build_boot_rom

__all__ = ["build_boot_rom"]
