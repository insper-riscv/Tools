"""Compiles bare-metal test sources into linked .elf/.bin."""

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
from riscv_tools.compiler.cxx import (
    CxxLibraryMissingError,
    cxx_enabled,
    cxx_flags,
    cxx_options,
    gxx_for,
    is_cxx_source,
    require_libstdcxx,
)
from riscv_tools.compiler.headers import canonical_march, parse_header

__all__ = [
    "BuildSetup",
    "CxxLibraryMissingError",
    "LinkSetup",
    "canonical_march",
    "compile_test",
    "cxx_enabled",
    "cxx_flags",
    "cxx_options",
    "elf_to_bin",
    "elf_to_verilog_hex",
    "gxx_for",
    "is_cxx_source",
    "libc_flags",
    "optimize_flags",
    "parse_header",
    "require_libstdcxx",
    "run_gcc",
]
