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
        # HTIF symbol every crt0-linked test binary defines and writes
        # a nonzero value to once done (see link.ld/crt0.S in the
        # consuming project) — Spike watches it to know when to
        # snapshot memory (see generate.py). Standard Spike/riscv-tests
        # convention, so "tohost" should rarely need overriding.
        "tohost_symbol": "tohost",
    },
}
