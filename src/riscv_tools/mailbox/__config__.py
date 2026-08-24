"""Defaults for the PASS/FAIL mailbox + restart "go" flag protocol
(see the consuming project's crt0.S/rv32_test.h). Overridden under
`memory:` / `quartus:` in a project's config.yaml."""

DEFAULTS = {
    "quartus": {
        "ram_mem_instance": 1,
        "poll_interval_seconds": 0.5,
    },
    "memory": {
        # Memory addresses are project-specific (depend on RAM depth)
        # — no sane default, every project must set these explicitly.
        "ram_base": None,
        "mailbox_addr": None,
        "go_flag_addr": None,
    },
}
