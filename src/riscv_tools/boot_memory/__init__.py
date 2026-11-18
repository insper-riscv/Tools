"""Builds the fixed, shared bootloader (boot_memory.S) once per run."""

from riscv_tools.boot_memory.core import (
    BootMemoryOptions,
    boot_gcc_args,
    build_boot_memory,
)

__all__ = ["BootMemoryOptions", "boot_gcc_args", "build_boot_memory"]
