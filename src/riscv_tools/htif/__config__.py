"""Define defaults for the HTIF tohost/fromhost protocol.

See the consuming project's crt0.S and rv32_test.h. Overridden under
`memory:` / `quartus:` in a project's config.yaml.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "quartus": {
        "ram_mem_instance": 1,
        "poll_interval_seconds": 0.5,
    },
    "memory": {
        # Memory addresses are project-specific (depend on RAM depth),
        # so there is no sane default and every project must set these.
        "ram_base": None,
        # HTIF: tohost (64 bits) and fromhost (the 8 bytes above it).
        "tohost_addr": None,
        "fromhost_addr": None,
    },
}
