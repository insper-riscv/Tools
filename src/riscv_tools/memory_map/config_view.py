"""The `memory` section of a project config, read from the platform map.

A project config names the platform file with `memory_map: <path>`. The
platform's `config` section says which regions are the ROM and the RAM
and which simulation memories take their address width from the map:

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_memory, rom, ram]
```

The base ISA of the platform's `profile` (`i` or `e`) becomes
`isa.base`, which picks `-march` and `-mabi` of the programs and of the
boot memory. A platform with an `address_bits` other than 32 also gives
`memory.addr_bits`, and one with an `rv64` profile gives `isa.xlen`.
The values come out as the `memory` keys the tools read
(`boot_memory_base`, `boot_memory_words`, `rom_base`, `rom_words`,
`ram_base`, `ram_words`, `tohost_addr` and `fromhost_addr`), as the
`TOHOST_ADDR` and `STDOUT_ADDR` environment of the simulation and as the
`sim.parameters.*_addr_width`, so no address or size is typed twice.
With a `memory` section (see `memory`) the parameters also carry the
choice of memories and caches, and `addr_widths` may be left out: it
then lists the boot memory and each internal memory.
"""

from pathlib import Path
from typing import Any

from riscv_tools.memory_map import memory as memory_choice
from riscv_tools.memory_map.banks import bank_list
from riscv_tools.memory_map.config_pkg import render_variant
from riscv_tools.memory_map.core import (
    DEFAULT_ADDRESS_BITS,
    address_bits,
    load_platform,
    platform_dict,
    platform_list,
    symbols,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.profile import resolve

DEFAULT_XLEN = 32


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
        The bases and the words of the memories, and `tohost_addr`,
        `fromhost_addr` and `launch_addr` when the map reserves them.
    """
    spec = platform_dict(platform, "config")
    boot = platform_list(platform, "regions")[0]["name"]
    rom, ram = spec["rom"], spec["ram"]
    memory = {
        "boot_memory_base": table[f"{boot}.base"],
        "boot_memory_words": table[f"{boot}.words"],
        "rom_base": table[f"{rom}.base"],
        "rom_words": table[f"{rom}.words"],
        "ram_base": table[f"{ram}.base"],
        "ram_words": table[f"{ram}.words"],
    }
    for key in ("tohost", "fromhost", "launch"):
        if f"{key}.base" in table:
            memory[f"{key}_addr"] = table[f"{key}.base"]
    return memory


def _parameters(
    platform: dict[str, Any], memory: dict[str, int]
) -> dict[str, str | bool]:
    """Read the generics of the simulation top off the map.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `config.addr_widths` lists the memories.
    memory : dict of {str: int}
        The `memory` keys (see `_memory`).

    Returns
    -------
    dict of {str: str or bool}
        The address widths and the generics of the memories and caches
        (see `memory.parameters`). The base and the extensions are not
        generics of the top: they reach the core through the
        `config_pkg` (see `_config_pkg`).
    """
    words = {
        "boot_memory": memory["boot_memory_words"],
        "rom": memory["rom_words"],
        "ram": memory["ram_words"],
    }
    parameters: dict[str, str | bool] = {
        f"{name}_addr_width": _width(words[name])
        for name in memory_choice.addr_width_names(platform)
    }
    parameters |= memory_choice.parameters(platform)
    return parameters


def _config_pkg(platform: dict[str, Any], platform_file: Path) -> str:
    """Render the `config_pkg` of the profile for the simulation.

    The base and the extensions of the core are constants of the
    `config_pkg`, not generics of the top, so the simulation of a
    profile other than the platform's own (`--profile`) compiles this
    text in place of the file of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_file : Path
        The platform YAML, named in the header of the package.

    Returns
    -------
    str
        The package, or an empty string when the platform asks for no
        `generate.config_pkg`.
    """
    if "config_pkg" not in platform_dict(platform, "generate"):
        return ""
    return render_variant(platform, platform_file, platform_file.parent)


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
    base, _, xlen = resolve(platform, platform_file)
    env = {
        key: f"0x{table[symbol]:08X}"
        for key, symbol in (
            ("TOHOST_ADDR", "tohost.base"),
            ("STDOUT_ADDR", "stdout.base"),
        )
        if symbol in table
    }
    sim: dict[str, Any] = {"parameters": _parameters(platform, memory)}
    if env:
        sim["env"] = env
    config_pkg = _config_pkg(platform, platform_file)
    if config_pkg:
        sim["config_pkg"] = config_pkg
    config: dict[str, Any] = {
        "memory": memory,
        "isa": {"base": base},
        "sim": sim,
    }
    # Só uma plataforma fora do padrão (32 bits de endereço, RV32) leva
    # as chaves novas, de modo que as demais geram o mesmo arquivo.
    bits = address_bits(platform)
    if bits != DEFAULT_ADDRESS_BITS:
        memory["addr_bits"] = bits
    if xlen != DEFAULT_XLEN:
        config["isa"]["xlen"] = xlen
    banks = bank_list(platform)
    if banks:
        config["flash"] = {
            "banks": [
                {
                    "name": str(bank["name"]),
                    "base": evaluate(bank["base"]),
                    "size": evaluate(bank["size"]),
                }
                for bank in banks
            ]
        }
    return config
