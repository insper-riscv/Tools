"""Define defaults for compiling test sources into ELF/bin/mif/hex.

A project's config.yaml overrides these under `isa:` / `toolchain:`.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "toolchain": {
        "gcc": "riscv32-unknown-elf-gcc",
        "objcopy": "riscv32-unknown-elf-objcopy",
        # C library the tests link against: "none" (-nostdlib, a project
        # supplies what it needs through paths.syscalls) or "picolibc"
        # (the toolchain's own, for a GCC built with it).
        "libc": "none",
        # A GCC specs file (path relative to the project root) that
        # describes the platform: it includes picolibc.specs and adds the
        # memory map and the crt0 to use (see insper-riscv/Testes'
        # rv32im-fpga.specs). When set, tests are compiled as hosted
        # programs with `--specs=<file>` and link against the toolchain's
        # own crt0 and linker script, so paths.crt0 and paths.linker_script
        # are not needed, and `libc` is ignored.
        "specs": None,
    },
    "isa": {
        "base": "i",  # always implied, never written in a test's header
        "default_ext": "",  # no "// RV32_EXT:" header -> plain rv32i
        # Canonical order standard RISC-V extension letters get sorted
        # into before being appended to the base ISA string, so
        # "// RV32_EXT: A,M" and "// RV32_EXT: M,A" both normalize to
        # the same march string.
        "canonical_order": "MAFDQLCBJTPVNH",
    },
    "paths": {
        # All project-specific (paths inside the CONSUMING repo, not
        # this package) — no sane generic default.
        "include_dir": None,
        # Optional: a project's own startup file and linker script. Leave
        # both unset with toolchain.specs, which selects the toolchain's.
        "crt0": None,
        "linker_script": None,
        # Optional: source files (relative to the project root) compiled
        # into every test, for the parts of the runtime that are the
        # platform's own (for instance the _exit the toolchain's crt0
        # ends in, and the write function of stdout). Not the boot ROM.
        "sources": [],
        "build_dir": None,
        # Each holds one <name>/ folder per test (src.c under c_dir,
        # src.S under asm_dir), optionally with a golden.json for
        # "memory"-kind tests (see cli._discover_tests) — no real/sim
        # split: a test's kind decides where it builds/runs (real
        # always; sim only for "unit"-kind, see cli.cmd_compile).
        "c_dir": None,
        "asm_dir": None,
    },
}
