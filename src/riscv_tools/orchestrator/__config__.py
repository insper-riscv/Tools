"""Define defaults for orchestrating a full real-hardware test run.

A project's config.yaml overrides these under `quartus:`.
"""

DEFAULTS = {
    "quartus": {
        # How long to wait after a full_reconfigure (fallback path
        # only; the JTAG-reload path polls tohost instead, see the
        # htif module) before reading tohost.
        "program_wait_seconds": 15,
        # Default per-test timeout if a test doesn't set its own
        # RV32_TIMEOUT_S header (see compiler.headers).
        "default_timeout_s": 15,
    },
}
