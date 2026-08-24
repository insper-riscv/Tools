"""Defaults for JTAG link concerns. A project's config.yaml overrides
these under its own `quartus:` section (see riscv_tools.settings)."""

DEFAULTS = {
    "quartus": {
        # The FPGA's own JTAG IDCODE string — unlike the "USB-Blaster
        # [<bus>-<port>]" cable name (auto-detected live, see
        # hardware.py), this doesn't drift across reboots/hub
        # renumbering. Every project must set this explicitly.
        "jtag_device": None,
    },
}
