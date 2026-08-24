"""Compiles a C source to human-readable RISC-V assembly, for inspecting codegen."""

from .core import c_to_asm

__all__ = ["c_to_asm"]
