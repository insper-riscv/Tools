"""The `memory` section of a project config, read from the platform map.

A project config names the platform file with `memory_map: <path>`. The
platform's `config` section says which regions are the ROM and the RAM
and which simulation memories take their address width from the map:

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_rom, rom, ram]
```

The values come out as the `memory` keys the tools read
(`boot_rom_base`, `boot_rom_words`, `rom_base`, `rom_words`, `ram_base`,
`ram_words`, `tohost_addr` and `fromhost_addr`) and as the
`sim.parameters.*_addr_width`, so no address or size is typed twice.
"""

from pathlib import Path
from typing import Any

from riscv_tools.memory_map.core import (
    load_platform,
    platform_dict,
    platform_list,
    symbols,
)


def _width(words: int) -> str:
    """Count the address bits of a memory of `words` words.

    Parameters
    ----------
    words : int
        The depth of the memory.

    Returns
    -------
    str
        The bits of the word address, as the generic string.
    """
    return str(max(words - 1, 0).bit_length())


def config_from_platform(platform_file: Path) -> dict[str, Any]:
    """Build the config keys that the platform map fixes.

    Parameters
    ----------
    platform_file : Path
        The platform YAML.

    Returns
    -------
    dict of {str: Any}
        A partial config with `memory` and, when the platform lists
        `addr_widths`, `sim.parameters`.
    """
    platform = load_platform(platform_file)
    table = symbols(platform)
    spec = platform_dict(platform, "config")
    boot = platform_list(platform, "regions")[0]["name"]
    rom, ram = spec["rom"], spec["ram"]
    memory: dict[str, int] = {
        "boot_rom_base": table[f"{boot}.base"],
        "boot_rom_words": table[f"{boot}.words"],
        "rom_base": table[f"{rom}.base"],
        "rom_words": table[f"{rom}.words"],
        "ram_base": table[f"{ram}.base"],
        "ram_words": table[f"{ram}.words"],
    }
    for key in ("tohost", "fromhost"):
        if f"{key}.base" in table:
            memory[f"{key}_addr"] = table[f"{key}.base"]
    words = {
        "boot_rom": memory["boot_rom_words"],
        "rom": memory["rom_words"],
        "ram": memory["ram_words"],
    }
    config: dict[str, Any] = {"memory": memory}
    widths = {
        f"{name}_addr_width": _width(words[name])
        for name in spec.get("addr_widths", [])
    }
    if widths:
        config["sim"] = {"parameters": widths}
    return config
