"""Define defaults for generating a golden reference dynamically via Spike.

See core.py. Overridden under `toolchain:` / `emulator:` in a project's
config.yaml.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
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
        # Source files (relative to the project root) linked into the ELF
        # Spike runs and not into the test's own image. A project whose
        # image ends in code that lives elsewhere on the hardware (a boot
        # ROM routine at a fixed address) gives Spike a stand-in here, plus
        # the tohost/fromhost symbols it needs. Empty: Spike runs the
        # test's own image (or, with the legacy paths.golden_linker_script,
        # the test linked with paths.boot_rom).
        "sources": [],
        # Extra gcc arguments for that ELF (for example a -D that makes
        # the platform's specs file leave the hardware's fixed address out).
        "gcc_flags": [],
    },
}
