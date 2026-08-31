"""Define defaults for compiling test sources into ELF/bin/mif/hex.

A project's config.yaml overrides these under `isa:` / `toolchain:`.
"""

DEFAULTS = {
    "toolchain": {
        "gcc": "riscv32-unknown-elf-gcc",
        "objcopy": "riscv32-unknown-elf-objcopy",
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
        "crt0": None,
        "linker_script": None,
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
