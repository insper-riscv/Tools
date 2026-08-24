"""Defaults for validating a RAM dump against a golden reference,
including generating that reference dynamically via Spike (see
generate.py and vendor/riscv-isa-sim). Overridden under `toolchain:` /
`emulator:` in a project's config.yaml."""

DEFAULTS = {
    "toolchain": {
        "nm": "riscv32-unknown-elf-nm",
    },
    "emulator": {
        # Path/name of the built `spike` binary — vendor/riscv-isa-sim
        # must be built first (./configure && make), no sane default
        # across workstations.
        "spike_bin": "spike",
        # Symbol every crt0-linked test binary jumps to once done
        # (RV32_PASS/RV32_FAIL, or main() returning) — used as Spike's
        # breakpoint to know when to snapshot memory (see generate.py).
        "restart_symbol": "rv32_wait_restart",
    },
}
