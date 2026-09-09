"""Define defaults for generating a golden reference dynamically via Spike.

See core.py and vendor/riscv-isa-sim, instead of a hand-written golden
JSON. Overridden under `toolchain:` / `emulator:` in a project's
config.yaml.
"""

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
        # snapshot memory (see core.py). Standard Spike/riscv-tests
        # convention, so "tohost" should rarely need overriding.
        "tohost_symbol": "tohost",
        # Symbol Spike starts execution at (generate_golden's own
        # entry_symbol) — "_start" (the usual crt0 entry label) unless
        # a project names it something else, e.g. a project with a
        # fixed shared bootloader whose own reset vector isn't called
        # "_start" (see cli.py's _generate_c_golden).
        "entry_symbol": "_start",
    },
}
