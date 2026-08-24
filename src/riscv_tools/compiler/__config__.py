"""Defaults for compiling test sources into ELF/bin/mif/hex. A
project's config.yaml overrides these under `isa:` / `toolchain:`."""

DEFAULTS = {
    "toolchain": {
        "gcc": "riscv32-unknown-elf-gcc",
        "objcopy": "riscv32-unknown-elf-objcopy",
    },
    "isa": {
        "base": "i",       # always implied, never written in a test's header
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
        "tests_real_dir": None,
        "tests_sim_dir": None,
        "golden_dir": None,
    },
}
