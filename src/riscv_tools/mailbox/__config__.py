"""Define defaults for the PASS/FAIL mailbox and restart protocol.

See the consuming project's crt0.S/rv32_test.h. Overridden under
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
        "mailbox_addr": None,
        "go_flag_addr": None,
    },
}
