"""Defaults for building/running the ACT4 architectural certification suite.

Overridden under `act:` in a project's config.yaml.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "act": {
        # vendor/riscv-arch-test — the ACT4 framework itself, a pinned
        # git submodule (see AGENTS.md: "config/*/ci.yaml plus each
        # run_cmd.txt"), relative to the project root.
        "vendor_dir": "vendor/riscv-arch-test",
        # This project's own ACT4 target config (test_config.yaml) —
        # project-specific, no sane default.
        "target_config": None,
        # Comma-separated extension list forwarded to ACT4's own
        # `make ... EXTENSIONS=`. Grows as the core gains extensions
        # (A next, most likely) — see rv32im-min.yaml's own history.
        "extensions": "I,M",
        # `make`'s own -j equivalent (0 = auto-detect CPU count, ACT4's
        # own default — see vendor/riscv-arch-test/Makefile: JOBS).
        "jobs": 0,
    },
}
