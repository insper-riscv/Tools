"""Compiles bare-metal test sources (.c/.S) into linked .elf/.bin."""

from .build import BuildSetup, compile_test, elf_to_verilog_hex, libc_flags
from .headers import canonical_march, parse_header

__all__ = [
    "BuildSetup",
    "canonical_march",
    "compile_test",
    "elf_to_verilog_hex",
    "libc_flags",
    "parse_header",
]
