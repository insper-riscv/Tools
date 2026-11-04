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

The base ISA of the platform's `profile` (`i` or `e`) becomes
`isa.base`, which picks `-march` and `-mabi` of the programs and of the
boot ROM.
The values come out as the `memory` keys the tools read
(`boot_rom_base`, `boot_rom_words`, `rom_base`, `rom_words`, `ram_base`,
`ram_words`, `tohost_addr` and `fromhost_addr`), as the `TOHOST_ADDR`
and `STDOUT_ADDR` environment of the simulation and as the
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
from riscv_tools.memory_map.profile import SWITCHES, resolve


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


def _memory(platform: dict[str, Any], table: dict[str, int]) -> dict[str, int]:
    """Read the `memory` keys of the config off the map.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: the `config` section names the ROM and RAM.
    table : dict of {str: int}
        The symbols of the map.

    Returns
    -------
    dict of {str: int}
        The bases and the words of the memories, and `tohost_addr` and
        `fromhost_addr` when the map reserves them.
    """
    spec = platform_dict(platform, "config")
    boot = platform_list(platform, "regions")[0]["name"]
    rom, ram = spec["rom"], spec["ram"]
    memory = {
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
    return memory


def _parameters(
    platform: dict[str, Any],
    memory: dict[str, int],
    generics: dict[str, bool | int],
) -> dict[str, str | bool]:
    """Read the generics of the simulation top off the map and profile.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `config.addr_widths` lists the memories.
    memory : dict of {str: int}
        The `memory` keys (see `_memory`).
    generics : dict of {str: bool or int}
        The generics of the profile.

    Returns
    -------
    dict of {str: str or bool}
        The address widths, `NUM_REGS` and one `HAS_*` per extension.
    """
    words = {
        "boot_rom": memory["boot_rom_words"],
        "rom": memory["rom_words"],
        "ram": memory["ram_words"],
    }
    parameters: dict[str, str | bool] = {
        f"{name}_addr_width": _width(words[name])
        for name in platform_dict(platform, "config").get("addr_widths", [])
    }
    parameters["NUM_REGS"] = str(generics["num_regs"])
    for key in SWITCHES:
        if key in generics:
            parameters[key.upper()] = bool(generics[key])
    return parameters


def config_from_platform(platform_file: Path) -> dict[str, Any]:
    """Build the config keys that the platform map fixes.

    Parameters
    ----------
    platform_file : Path
        The platform YAML.

    Returns
    -------
    dict of {str: Any}
        A partial config with `isa`, `memory` and `sim` (the `env` of
        the host words and the `parameters` of the simulation top).
    """
    platform = load_platform(platform_file)
    table = symbols(platform)
    memory = _memory(platform, table)
    base, generics = resolve(platform, platform_file)
    env = {
        key: f"0x{table[symbol]:08X}"
        for key, symbol in (
            ("TOHOST_ADDR", "tohost.base"),
            ("STDOUT_ADDR", "stdout.base"),
        )
        if symbol in table
    }
    sim: dict[str, Any] = {
        "parameters": _parameters(platform, memory, generics)
    }
    if env:
        sim["env"] = env
    return {"memory": memory, "isa": {"base": base}, "sim": sim}
