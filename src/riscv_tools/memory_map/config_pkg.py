"""Write the `config_pkg`, the VHDL package of constants of a platform.

The package is the single mirror, in VHDL, of what the platform YAML
chooses: the base ISA (`IS_64`, `IS_E`), the width of the
physical address (`ADDR_BITS`), one `HAS_*` constant for each
extension, cache and peripheral that talks to the core, the memory map
of the core (BOOT_MEMORY, FLASH and RAM, in bytes) and the checks of the
combination. The peripherals of the SoC are in the package of the map
(`riscv_tools.memory_map.generate`).
It is a package of constants, one file for each platform, because the
Quartus Lite refuses a generic package.

The unit has the name `config_pkg`, the same as the default package of
the Common-Components, so the generated file takes the place of the
default one in the list of sources (see `riscv_tools.sources`). It is
written next to the package of the map (`generate.vhdl`), which keeps
the constants that are not in it, under `generate.config_pkg`:

```yaml
generate:
  config_pkg:
    path: rtl/config_pkg.vhd
```

`riscv-tools generate-config-pkg` writes the package of a platform or
of a variant of it (`--set IS_64=true --set ADDR_BITS=40`), for the
formal proof and for the matrix of profiles of the Core.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from riscv_tools.memory_map import memory as memory_choice
from riscv_tools.memory_map.core import (
    address_bits,
    peripheral_list,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.problems import platform_problems
from riscv_tools.memory_map.profile import (
    RV32_XLEN,
    RV64_XLEN,
    SWITCHES,
    resolve,
)
from riscv_tools.memory_map.symbol_table import symbol_table

PACKAGE = "config_pkg"
TEMPLATE = Path(__file__).resolve().parent / "templates" / "config_pkg.vhd.in"

# Constante do pacote de cada periférico que fala com o núcleo e o nome
# dele em `peripherals`.
PERIPHERALS = {
    "HAS_TIMER": "TIMER",
    "HAS_GPIO": "GPIO",
    "HAS_CLINT": "CLINT",
    "HAS_PLIC": "PLIC",
}
_HEADER = """\
-- ============================================================================
-- Pacote de configuração da plataforma (constantes de elaboração)
--
-- Gerado por `riscv-tools` a partir de {source}.
-- Não edite à mão: mude o YAML da plataforma e gere de novo.{variant}
--
-- A unidade tem o nome do pacote padrão do Common-Components e as mesmas
-- constantes e tipos, então esta versão ocupa o lugar dele na lista de fontes.
-- ============================================================================

"""


@dataclass(frozen=True)
class Config:
    """The choices of one platform that the `config_pkg` mirrors.

    Parameters
    ----------
    is_64 : bool
        The base is RV64.
    is_e : bool
        The base is E (16 registers).
    address_bits : int
        The width of the physical address.
    flags : dict of {str: bool}
        Every `HAS_*` constant, in the order of the package: the
        extensions, the caches and the peripherals of the core.
    flash_on_bus : bool
        The FLASH is reached through the bus (`FLASH_ON_BUS`).
    ram_on_bus : bool
        The RAM is reached through the bus (`RAM_ON_BUS`).
    boot_bits : int
        The exponent of the size of the BOOT_MEMORY.
    cache_window_bits : int
        The width of the window of the tag of the caches, the same for
        `I_CACHE_WINDOW_BITS` and `D_CACHE_WINDOW_BITS`.
    addresses : dict of {str: int}
        `FLASH_BASE`, `FLASH_END`, `RAM_BASE` and `RAM_END`, in bytes.
    """

    is_64: bool
    is_e: bool
    address_bits: int
    flags: dict[str, bool]
    flash_on_bus: bool
    ram_on_bus: bool
    boot_bits: int
    cache_window_bits: int
    addresses: dict[str, int]


def _override_value(item: str, name: str, text: str) -> bool | int:
    """Read the value of one `--set` pair.

    Parameters
    ----------
    item : str
        The pair as written, for the messages.
    name : str
        The constant, in upper case.
    text : str
        The value, in lower case.

    Returns
    -------
    bool or int
        An integer for `ADDR_BITS`, else a boolean.

    Raises
    ------
    ValueError
        If the value is not of the type of the constant.
    """
    if name == "ADDR_BITS":
        if not text.isdecimal():
            raise ValueError(f"--set {item!r}: an integer is needed")
        return int(text)
    if text not in ("true", "false"):
        raise ValueError(f"--set {item!r}: true or false is needed")
    return text == "true"


def parse_overrides(items: list[str]) -> dict[str, bool | int]:
    """Read the `--set NAME=VALUE` pairs of a variant.

    Parameters
    ----------
    items : list of str
        The pairs: `ADDR_BITS` takes an integer and every other name a
        boolean (`true` or `false`).

    Returns
    -------
    dict of {str: bool or int}
        The value of each name.

    Raises
    ------
    ValueError
        If a pair is malformed or a value is not of the type of its
        name.
    """
    found: dict[str, bool | int] = {}
    for item in items:
        name, sep, text = item.partition("=")
        name, text = name.strip().upper(), text.strip().lower()
        if not sep or not name:
            raise ValueError(f"--set {item!r} must be NAME=VALUE")
        found[name] = _override_value(item, name, text)
    return found


def _vhdl_spec(platform: dict[str, Any]) -> dict[str, Any]:
    """Read the `generate.vhdl` section, which names the ROM and RAM."""
    wanted = platform_dict(platform, "generate")
    return cast(dict[str, Any], wanted.get("vhdl") or {})


def _rom_ram(platform: dict[str, Any]) -> tuple[str, str]:
    """Find the regions that are the ROM and the RAM.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `generate.vhdl` or `config` names them.

    Returns
    -------
    tuple of (str, str)
        The name of the ROM region and of the RAM region.

    Raises
    ------
    ValueError
        If the platform names neither.
    """
    spec = _vhdl_spec(platform)
    config = platform_dict(platform, "config")
    rom = spec.get("rom") or config.get("rom")
    ram = spec.get("ram") or config.get("ram")
    if not rom or not ram:
        raise ValueError(
            "the config_pkg needs the ROM and the RAM: name them in "
            "`generate.vhdl` or `config` as `rom` and `ram`"
        )
    return str(rom), str(ram)


def _flags(
    platform: dict[str, Any], generics: dict[str, bool | int]
) -> dict[str, bool]:
    """Collect the `HAS_*` constants of the extensions and the rest.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}
        The generics of the profile.

    Returns
    -------
    dict of {str: bool}
        The extensions of `SWITCHES`, then `HAS_ICACHE` and
        `HAS_DCACHE`, then one constant for each name of `PERIPHERALS`.
    """
    choice = memory_choice.resolve(platform)
    names = {str(p["name"]) for p in peripheral_list(platform)}
    flags = {key.upper(): bool(generics.get(key)) for key in SWITCHES}
    flags["HAS_ICACHE"] = choice is not None and choice.has_icache
    flags["HAS_DCACHE"] = choice is not None and choice.has_dcache
    return flags | {flag: name in names for flag, name in PERIPHERALS.items()}


def _apply(
    flags: dict[str, bool], overrides: dict[str, bool | int]
) -> dict[str, bool]:
    """Replace the flags that a variant sets.

    Parameters
    ----------
    flags : dict of {str: bool}
        The flags of the platform.
    overrides : dict of {str: bool or int}
        The variant: `IS_64`, `IS_E` and `ADDR_BITS` are read by the
        caller, the other names must be flags.

    Returns
    -------
    dict of {str: bool}
        The flags with the variant applied.

    Raises
    ------
    ValueError
        If a name is neither a flag nor one of the three above.
    """
    own = {"IS_64", "IS_E", "ADDR_BITS"}
    unknown = sorted(set(overrides) - own - set(flags))
    if unknown:
        raise ValueError(
            f"--set {', '.join(unknown)}: not a constant of the "
            "config_pkg that a variant can change"
        )
    return flags | {
        key: bool(value) for key, value in overrides.items() if key in flags
    }


def _addresses(
    platform: dict[str, Any], table: dict[str, int]
) -> dict[str, int]:
    """Read the bases and ends of the FLASH and of the RAM, in bytes.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    table : dict of {str: int}
        The symbols of the map.

    Returns
    -------
    dict of {str: int}
        `FLASH_BASE`, `FLASH_END`, `RAM_BASE` and `RAM_END`.
    """
    rom, ram = _rom_ram(platform)
    return {
        "FLASH_BASE": table[f"{rom}.base"],
        "FLASH_END": table[f"{rom}.end"],
        "RAM_BASE": table[f"{ram}.base"],
        "RAM_END": table[f"{ram}.end"],
    }


def _relocated(platform: dict[str, Any], bits: int) -> dict[str, Any]:
    """Give the platform another address width and move its peripherals.

    A peripheral in the upper half of the old space keeps its place
    relative to the upper half of the new one, scaled the way the
    window of sixteen slots scales: the slot (`address_bits - 4` bits
    up) is kept and the bytes inside the slot too.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    bits : int
        The width of the physical address of the variant.

    Returns
    -------
    dict of {str: Any}
        A copy with `address_bits` and the bases of the peripherals
        replaced.

    Raises
    ------
    ValueError
        If `bits` is not an integer from 16 to 64.
    """
    moved = {**platform, "address_bits": bits}
    address_bits(moved)
    old = address_bits(platform)
    half, slot = 1 << (old - 1), 1 << (old - 4)
    new_half = 1 << (bits - 1)
    items: list[dict[str, Any]] = []
    for periph in platform_list(platform, "peripherals"):
        base = evaluate(periph["base"])
        if base >= half:
            offset = base - half
            base = new_half + ((offset // slot) << (bits - 4)) + offset % slot
        items.append({**periph, "base": base})
    moved["peripherals"] = items
    return moved


def _bus_problem(flags: dict[str, bool], flash: bool, ram: bool) -> str:
    """Name the cache that a variant put over a memory off the bus.

    Parameters
    ----------
    flags : dict of {str: bool}
        The flags, with the variant applied.
    flash : bool
        The FLASH is on the bus.
    ram : bool
        The RAM is on the bus.

    Returns
    -------
    str
        The message of the first cache that lacks its memory on the
        bus; empty when none does.
    """
    if flags["HAS_ICACHE"] and not flash:
        return "V-C1 HAS_ICACHE needs FLASH_ON_BUS"
    if flags["HAS_DCACHE"] and not ram:
        return "V-C2 HAS_DCACHE needs RAM_ON_BUS"
    return ""


def build_config(
    platform: dict[str, Any],
    platform_file: Path,
    overrides: dict[str, bool | int] | None = None,
) -> Config:
    """Read the choices of a platform, or of a variant of it.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_file : Path
        The platform YAML, which locates the profile specification.
    overrides : dict of {str: bool or int}, optional
        The variant (see `parse_overrides`), checked as a platform of
        its own: V-A1 to V-A6 hold for its `ADDR_BITS` and `IS_64`, and
        its peripherals move to the upper half of that width.

    Returns
    -------
    Config
        The choices.

    Raises
    ------
    ValueError
        If the variant names an unknown constant or the platform (with
        the variant applied) is inconsistent.
    """
    overrides = overrides or {}
    if "ADDR_BITS" in overrides:
        platform = _relocated(platform, int(overrides["ADDR_BITS"]))
    base, generics, xlen = resolve(platform, platform_file)
    generics = generics | {
        key: bool(overrides[key.upper()])
        for key in SWITCHES
        if key.upper() in overrides
    }
    xlen = (
        RV64_XLEN if overrides.get("IS_64", xlen == RV64_XLEN) else RV32_XLEN
    )
    problems = platform_problems(platform, generics, xlen)
    if problems:
        raise ValueError("; ".join(str(p) for p in problems))
    table = symbol_table(platform)
    flags = _apply(_flags(platform, generics), overrides)
    boot = platform_list(platform, "regions")[0]["name"]
    flash, ram = memory_choice.externals(
        _vhdl_spec(platform), memory_choice.resolve(platform)
    )
    bad = _bus_problem(flags, bool(flash), bool(ram))
    if bad:
        raise ValueError(bad)
    return Config(
        is_64=xlen == RV64_XLEN,
        is_e=bool(overrides.get("IS_E", base == "e")),
        address_bits=address_bits(platform),
        flags=flags,
        flash_on_bus=bool(flash),
        ram_on_bus=bool(ram),
        boot_bits=(table[f"{boot}.size"] - 1).bit_length(),
        cache_window_bits=memory_choice.cache_window_bits(platform),
        addresses=_addresses(platform, table),
    )


def _address(value: int, bits: int) -> str:
    """Write a byte address as a `map_addr_t` literal.

    Parameters
    ----------
    value : int
        The address in bytes, at most `2**bits`.
    bits : int
        The width of the physical address.

    Returns
    -------
    str
        The expression: a hexadecimal literal of the digits that `bits`
        take (eight for 32 bits) or the value needs, resized to the
        `bits + 1` bits of `map_addr_t`.
    """
    digits = max((bits + 3) // 4, len(f"{value:X}"))
    return f'resize(unsigned\'(x"{value:0{digits}X}"), ADDR_BITS + 1)'


def render_config_pkg(
    config: Config,
    source: str,
    overrides: dict[str, bool | int] | None = None,
) -> str:
    """Render the `config_pkg` of a platform.

    Parameters
    ----------
    config : Config
        The choices (see `build_config`).
    source : str
        The platform file, for the header.
    overrides : dict of {str: bool or int}, optional
        The variant, named in the header.

    Returns
    -------
    str
        The file: the header, then the text of the package of the
        Common-Components with the values of the platform.
    """
    variant = "".join(
        f"\n-- Variante: {key}={str(value).lower()}."
        for key, value in (overrides or {}).items()
    )
    bits = config.address_bits
    fields: dict[str, str] = {
        key.lower(): str(value).lower() for key, value in config.flags.items()
    }
    fields |= {
        "is_64": str(config.is_64).lower(),
        "is_e": str(config.is_e).lower(),
        "addr_bits": str(bits),
        "boot_memory_bits": str(config.boot_bits),
        "i_cache_window_bits": str(config.cache_window_bits),
        "d_cache_window_bits": str(config.cache_window_bits),
        "flash_on_bus": str(config.flash_on_bus).lower(),
        "ram_on_bus": str(config.ram_on_bus).lower(),
    }
    fields |= {
        key.lower(): _address(value, bits)
        for key, value in config.addresses.items()
    }
    body = TEMPLATE.read_text(encoding="utf-8").format(**fields)
    return _HEADER.format(source=source, variant=variant) + body


def source_name(platform_file: Path, root: Path) -> str:
    """Name the platform file for the header of a generated file.

    Parameters
    ----------
    platform_file : Path
        The platform YAML.
    root : Path
        The project root.

    Returns
    -------
    str
        The path relative to the root, or the file name when the
        platform is outside it.
    """
    try:
        return str(platform_file.relative_to(root))
    except ValueError:
        return platform_file.name


def render_variant(
    platform: dict[str, Any],
    platform_file: Path,
    root: Path,
    overrides: dict[str, bool | int] | None = None,
) -> str:
    """Render the `config_pkg` of a platform or of a variant of it.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_file : Path
        The platform YAML.
    root : Path
        The project root, for the header.
    overrides : dict of {str: bool or int}, optional
        The variant (see `parse_overrides`).

    Returns
    -------
    str
        The file.

    Raises
    ------
    ValueError
        If the platform or the variant is inconsistent.
    """
    config = build_config(platform, platform_file, overrides)
    return render_config_pkg(
        config, source_name(platform_file, root), overrides
    )
