"""Define defaults for generating a golden reference dynamically via Spike.

See core.py. Overridden under `toolchain:` / `emulator:` in a project's
config.yaml.
"""

DEFAULTS = {
    "toolchain": {
        "nm": "riscv32-unknown-elf-nm",
    },
    "emulator": {
        # Name or path of the `spike` binary. The default finds the one
        # the workstation's toolchain install puts on PATH.
        "spike_bin": "spike",
        # HTIF symbol every crt0-linked test binary defines and writes
        # a nonzero value to once done (see link.ld/crt0.S in the
        # consuming project); Spike exits on it. Standard
        # Spike/riscv-tests convention, so "tohost" should rarely need
        # overriding.
        "tohost_symbol": "tohost",
        # Symbol Spike starts execution at (generate_golden's own
        # entry_symbol): "_start" (the usual crt0 entry label) unless
        # a project names it something else, e.g. a project with a
        # fixed shared bootloader whose own reset vector isn't called
        # "_start".
        "entry_symbol": "_start",
        # Seconds to wait for a test to write tohost before giving up.
        "timeout_s": 60,
    },
}
