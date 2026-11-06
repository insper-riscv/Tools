"""Define defaults for JTAG link concerns.

A project's config.yaml overrides these under its own `quartus:`
section (see riscv_tools.settings).
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "quartus": {
        # The FPGA's own JTAG IDCODE string, unlike the "USB-Blaster
        # [<bus>-<port>]" cable name (auto-detected live, see
        # hardware.py), this doesn't drift across reboots/hub
        # renumbering. Every project must set this explicitly.
        "jtag_device": None,
        # Index of the Virtual JTAG instance of the SDRAM debug port
        # (sld_instance_index in the platform's top). The default, 0, is
        # the only instance of a platform without the FLASH loader; a
        # platform with both gives the debug port another index.
        "sdram_debug_instance": 0,
    },
}
