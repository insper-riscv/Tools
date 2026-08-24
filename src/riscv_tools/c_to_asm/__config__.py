"""Defaults for compiling a C source straight to RISC-V assembly. A
project's config.yaml overrides these under `toolchain:` / `isa:`
(shared with the `compiler` module — same toolchain, same ISA rules,
different output)."""

DEFAULTS = {
    "toolchain": {
        "gcc": "riscv32-unknown-elf-gcc",
    },
    "isa": {
        "base": "i",
        "canonical_order": "MAFDQLCBJTPVNH",
    },
}
