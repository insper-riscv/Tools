"""Compiles bare-metal test sources (.c/.S) into linked .elf/.bin."""

from riscv_tools.compiler.build import (
    BuildSetup,
    LinkSetup,
    compile_test,
    elf_to_bin,
    elf_to_verilog_hex,
    libc_flags,
    optimize_flags,
    run_gcc,
)
from riscv_tools.compiler.headers import canonical_march, parse_header

__all__ = [
    "BuildSetup",
    "LinkSetup",
    "canonical_march",
    "compile_test",
    "elf_to_bin",
    "elf_to_verilog_hex",
    "libc_flags",
    "optimize_flags",
    "parse_header",
    "run_gcc",
]
