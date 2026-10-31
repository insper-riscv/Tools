"""Compiles a C source to readable RISC-V assembly (codegen check)."""

from .core import c_to_asm

__all__ = ["c_to_asm"]
