"""Builds the fixed, shared bootloader (boot_memory.S) once per run."""

from riscv_tools.boot_memory.core import BootMemoryOptions, build_boot_memory

__all__ = ["BootMemoryOptions", "build_boot_memory"]
