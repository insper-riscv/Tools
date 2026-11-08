"""The `memory` section of a platform: memories and caches.

The platform picks four independent choices: whether the ROM (the
FLASH) and the RAM are outside the chip, and whether an instruction
cache (`icache`, the $I) and a data cache (`dcache`, the $D) exist.
Sixteen combinations come out of them.

```yaml
memory:
  rom:    {external: true}
  ram:    {external: true}
  icache: {enabled: true, size_bits: 4096}
  dcache: {enabled: true, size_bits: 4096}
```

Nothing has a default: a missing field is an error, so a platform never
builds a combination other than the one its author wrote. `size_bits`
is only needed when the cache is enabled.

`--memory` of the command line replaces fields of the section for one
run, so a matrix of tests runs the same platform over the sixteen
combinations. Its syntax is a comma list of `key=value`:

| Key | Values |
| :--- | :--- |
| `rom`, `ram` | `int` or `ext` |
| `icache`, `dcache` | `on`, `off` or a size in bits (turns it on) |

A key that is not named keeps the platform's choice. A platform
without a `memory` section needs the four keys. `on` without a size
takes the `size_bits` of the platform, or 4096 when it has none.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.memory_map.core import (
    Mismatch,
    address_bits,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate

MIN_CACHE_BITS = 256
DEFAULT_CACHE_BITS = 4096
MIN_WINDOW_BITS = 26
MAX_WINDOW_BITS = 29
ROUTER_WINDOW_KIB = 1024
PAGE = 4096

_FIELDS = {
    "rom": ("external", "backend", "device", "latency", "sector_bytes"),
    "ram": ("external", "backend", "device", "latency"),
    "icache": ("enabled", "size_bits"),
    "dcache": ("enabled", "size_bits"),
}
_LOCATIONS = {
    "int": False,
    "internal": False,
    "ext": True,
    "external": True,
}
_SWITCHES = {"on": True, "off": False}

_override: list[dict[str, dict[str, Any]] | None] = [None]


@dataclass(frozen=True)
class Memory:
    """The memories and caches a platform chose.

    Parameters
    ----------
    rom_external : bool
        The ROM sits outside the chip.
    ram_external : bool
        The RAM sits outside the chip.
    has_icache : bool
        The instruction cache exists.
    has_dcache : bool
        The data cache exists.
    icache_size_bits : int
        The size of the instruction cache in bits (256 without one).
    dcache_size_bits : int
        The size of the data cache in bits (256 without one).
    """

    rom_external: bool
    ram_external: bool
    has_icache: bool
    has_dcache: bool
    icache_size_bits: int
    dcache_size_bits: int

    @property
    def rom_via_port(self) -> bool:
        """Say whether the core reaches the ROM through its port.

        Returns
        -------
        bool
            True when the ROM is external or sits behind the $I.
        """
        return self.rom_external or self.has_icache

    @property
    def ram_via_port(self) -> bool:
        """Say whether the core reaches the RAM through its port.

        Returns
        -------
        bool
            True when the RAM is external or sits behind the $D.
        """
        return self.ram_external or self.has_dcache


def _entry(key: str, value: str) -> dict[str, Any]:
    """Turn one `key=value` of `--memory` into a section entry.

    Parameters
    ----------
    key : str
        `rom`, `ram`, `icache` or `dcache`.
    value : str
        What follows the `=`.

    Returns
    -------
    dict of {str: Any}
        The fields to merge into the entry of the section.

    Raises
    ------
    ValueError
        If the key or the value is not valid.
    """
    if key not in _FIELDS:
        raise ValueError(
            f"--memory: unknown key {key!r} (use rom, ram, icache, dcache)"
        )
    if key in ("rom", "ram") and value in _LOCATIONS:
        return {"external": _LOCATIONS[value]}
    if key in ("icache", "dcache") and value in _SWITCHES:
        return {"enabled": _SWITCHES[value]}
    if key in ("icache", "dcache") and value.isdecimal():
        return {"enabled": True, "size_bits": int(value)}
    want = "int or ext" if key in ("rom", "ram") else "on, off or a size"
    raise ValueError(f"--memory: {key}={value!r} is not valid (use {want})")


def parse_override(text: str) -> dict[str, dict[str, Any]]:
    """Read the value of `--memory`.

    Parameters
    ----------
    text : str
        A comma list such as `rom=ext,ram=int,icache=on,dcache=off`.

    Returns
    -------
    dict of {str: dict of {str: Any}}
        The entries of the section the text names.

    Raises
    ------
    ValueError
        If a pair is malformed, repeated, or has an unknown key or
        value.
    """
    out: dict[str, dict[str, Any]] = {}
    for pair in text.split(","):
        key, sign, value = pair.strip().partition("=")
        if not sign:
            raise ValueError(f"--memory: {pair!r} is not key=value")
        if key in out:
            raise ValueError(f"--memory: {key!r} is given twice")
        out[key] = _entry(key, value.strip().lower())
    return out


def set_override(text: str | None) -> None:
    """Replace fields of the `memory` of the platforms read from now on.

    Parameters
    ----------
    text : str or None
        The value of `--memory`, or None to follow each platform.

    Raises
    ------
    ValueError
        If the text is not valid (see `parse_override`).
    """
    _override[0] = None if text is None else parse_override(text)


def _merged(platform: dict[str, Any]) -> Any:
    """Lay the override over the `memory` section of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    Any
        The section as the platform wrote it when there is no
        override, None when neither exists, otherwise the merged
        mapping.
    """
    section = platform.get("memory")
    override = _override[0]
    if override is None or not isinstance(section or {}, dict):
        return section
    merged = deepcopy(cast(dict[str, Any], section or {}))
    for key, entry in override.items():
        old = merged.get(key)
        merged[key] = (old if isinstance(old, dict) else {}) | entry
        if key.endswith("cache") and merged[key].get("enabled"):
            merged[key].setdefault("size_bits", DEFAULT_CACHE_BITS)
    return merged


def declared(platform: dict[str, Any]) -> bool:
    """Say whether the platform (or the command line) has a `memory`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when a `memory` section is to be read.
    """
    return _merged(platform) is not None


def _problem(detail: str) -> Mismatch:
    """Wrap a message as a problem of the memory choice.

    Parameters
    ----------
    detail : str
        What is wrong.

    Returns
    -------
    Mismatch
        The problem.
    """
    return Mismatch("memory", "", detail)


def _flag(
    raw: dict[str, Any], key: str, field: str, problems: list[Mismatch]
) -> bool:
    """Read one boolean field of the section.

    Parameters
    ----------
    raw : dict of {str: Any}
        The merged section.
    key : str
        `rom`, `ram`, `icache` or `dcache`.
    field : str
        `external` or `enabled`.
    problems : list of Mismatch
        Where a missing or malformed field is reported.

    Returns
    -------
    bool
        The value; False when it is not valid.
    """
    entry = raw.get(key)
    fields = cast(dict[str, Any], entry) if isinstance(entry, dict) else {}
    value = fields.get(field)
    if not isinstance(value, bool):
        problems.append(
            _problem(f"memory.{key}.{field} is required (true or false)")
        )
        return False
    return value


def _bits(
    raw: dict[str, Any], key: str, enabled: bool, problems: list[Mismatch]
) -> int:
    """Read the size of a cache.

    Parameters
    ----------
    raw : dict of {str: Any}
        The merged section.
    key : str
        `icache` or `dcache`.
    enabled : bool
        Whether the cache exists.
    problems : list of Mismatch
        Where a missing or invalid size is reported.

    Returns
    -------
    int
        `size_bits` of an enabled cache, the minimum otherwise.
    """
    entry = raw.get(key)
    fields = cast(dict[str, Any], entry) if isinstance(entry, dict) else {}
    value = fields.get("size_bits")
    if value is None:
        if enabled:
            problems.append(
                _problem(f"memory.{key}.size_bits is required when enabled")
            )
        return MIN_CACHE_BITS
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_CACHE_BITS
        or value & (value - 1)
    ):
        problems.append(
            _problem(
                f"memory.{key}.size_bits ({value!r}) must be a power of "
                f"two of at least {MIN_CACHE_BITS}"
            )
        )
        return MIN_CACHE_BITS
    return value if enabled else MIN_CACHE_BITS


def _unknown(raw: dict[str, Any]) -> list[Mismatch]:
    """Find keys of the section that no combination uses.

    Parameters
    ----------
    raw : dict of {str: Any}
        The merged section.

    Returns
    -------
    list of Mismatch
        One per unknown key.
    """
    problems = [
        _problem(f"memory.{key} is not a memory choice")
        for key in raw
        if key not in _FIELDS
    ]
    for key, fields in _FIELDS.items():
        entry = raw.get(key)
        if isinstance(entry, dict):
            problems += [
                _problem(f"memory.{key}.{field} is not a field of {key}")
                for field in cast(dict[str, Any], entry)
                if field not in fields
            ]
    return problems


def read(platform: dict[str, Any]) -> tuple[Memory | None, list[Mismatch]]:
    """Read the memory choice and check that it is well formed.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    tuple of (Memory or None, list of Mismatch)
        The choice (None when the platform and the command line leave
        it out) and the problems of its fields.
    """
    raw = _merged(platform)
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        return None, [_problem("memory must be a mapping")]
    section = cast(dict[str, Any], raw)
    problems = _unknown(section)
    has_i = _flag(section, "icache", "enabled", problems)
    has_d = _flag(section, "dcache", "enabled", problems)
    memory = Memory(
        rom_external=_flag(section, "rom", "external", problems),
        ram_external=_flag(section, "ram", "external", problems),
        has_icache=has_i,
        has_dcache=has_d,
        icache_size_bits=_bits(section, "icache", has_i, problems),
        dcache_size_bits=_bits(section, "dcache", has_d, problems),
    )
    return memory, problems


def resolve(platform: dict[str, Any]) -> Memory | None:
    """Read the memory choice, which must be well formed.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    Memory or None
        The choice; None when the platform leaves it out.

    Raises
    ------
    ValueError
        If a field is missing or invalid.
    """
    memory, problems = read(platform)
    if problems:
        raise ValueError("; ".join(str(p) for p in problems))
    return memory


def _region_span(
    platform: dict[str, Any], key: str
) -> tuple[str, int, int] | None:
    """Find the region the platform names as its ROM or its RAM.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `config` or `generate.vhdl` names the
        regions in `rom` and `ram`.
    key : str
        `rom` or `ram`.

    Returns
    -------
    tuple of (str, int, int) or None
        The name, base and size of the region; None when the platform
        does not name it.
    """
    vhdl = cast(
        dict[str, Any], platform_dict(platform, "generate").get("vhdl") or {}
    )
    name = platform_dict(platform, "config").get(key) or vhdl.get(key)
    for region in platform_list(platform, "regions"):
        if region["name"] == name:
            return (
                str(name),
                evaluate(region["base"]),
                evaluate(region["size"]),
            )
    return None


def _fits(regions: list[tuple[str, int, int]], bits: int) -> bool:
    """Say whether every region sits inside one aligned window.

    Parameters
    ----------
    regions : list of tuple of (str, int, int)
        The name, base and size of the regions.
    bits : int
        The width of the window: it spans `2**bits` bytes.

    Returns
    -------
    bool
        True when no region crosses a multiple of the window.
    """
    return all(
        base >> bits == (base + size - 1) >> bits for _, base, size in regions
    )


def window_bits(
    rom: tuple[str, int, int] | None, ram: tuple[str, int, int] | None
) -> int | None:
    """Find the narrowest tag window that holds the regions.

    Parameters
    ----------
    rom : tuple of (str, int, int) or None
        The ROM region, when named.
    ram : tuple of (str, int, int) or None
        The RAM region, when named.

    Returns
    -------
    int or None
        The smallest width from `MIN_WINDOW_BITS` (64 MiB) to
        `MAX_WINDOW_BITS` (512 MiB) such that each region sits in one
        aligned window of `2**width` bytes; None when none does.
    """
    regions = [r for r in (rom, ram) if r]
    for bits in range(MIN_WINDOW_BITS, MAX_WINDOW_BITS + 1):
        if _fits(regions, bits):
            return bits
    return None


def cache_window_bits(platform: dict[str, Any]) -> int:
    """Name the tag window that the map of the platform needs.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    int
        The width in bits of the window of the tag of the caches
        (`MIN_WINDOW_BITS` when no region needs more, and also when the
        regions fit no window, which `problems` rejects under a cache),
        never above `address_bits`: a platform whose address space is
        narrower than the window has the whole space as its window.
    """
    found = window_bits(
        _region_span(platform, "rom"), _region_span(platform, "ram")
    )
    bits = MIN_WINDOW_BITS if found is None else found
    return min(bits, address_bits(platform))


def _window_problems(
    memory: Memory,
    rom: tuple[str, int, int] | None,
    ram: tuple[str, int, int] | None,
) -> list[Mismatch]:
    """Check each region fits one aligned window of the cache tag."""
    if not (memory.has_icache or memory.has_dcache):
        return []
    if window_bits(rom, ram) is not None:
        return []
    return [
        _problem(
            f"region {name} does not fit one aligned "
            f"{1 << (MAX_WINDOW_BITS - 20)} MiB window, "
            "which the tag of the caches needs"
        )
        for name, base, size in (r for r in (rom, ram) if r)
        if not _fits([(name, base, size)], MAX_WINDOW_BITS)
    ]


def _cache_problems(
    memory: Memory,
    rom: tuple[str, int, int] | None,
    ram: tuple[str, int, int] | None,
) -> list[Mismatch]:
    """Check what the tags of the caches and the router impose (V3, V4).

    Parameters
    ----------
    memory : Memory
        The choice.
    rom : tuple of (str, int, int) or None
        The ROM region, when named.
    ram : tuple of (str, int, int) or None
        The RAM region, when named.

    Returns
    -------
    list of Mismatch
        A region that fits no aligned window of the cache tag, and a
        ROM larger than the window of the router.
    """
    problems = _window_problems(memory, rom, ram)
    if memory.rom_via_port and rom and rom[2] > ROUTER_WINDOW_KIB * 1024:
        problems.append(
            _problem(
                f"ROM {rom[0]} is larger than the {ROUTER_WINDOW_KIB} "
                "KiB window of the region router"
            )
        )
    return problems


def _exec_problems(
    memory: Memory,
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None,
) -> list[Mismatch]:
    """Check the executable regions in the RAM (V5, V7).

    Parameters
    ----------
    memory : Memory
        The choice.
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int} or None
        The generics of the profile; None skips the Zifencei check.

    Returns
    -------
    list of Mismatch
        Code in the RAM needs the RAM and the instruction fetch
        reached through the port of the core, and a $I over it needs
        Zifencei in the profile.
    """
    code = [
        r["name"]
        for r in platform_list(platform, "regions")
        if r.get("kind") == "ram" and r.get("exec")
    ]
    if not code:
        return []
    problems: list[Mismatch] = []
    if not (memory.ram_external and memory.rom_via_port):
        problems.append(
            _problem(
                f"region {code[0]} is executable in the RAM, which needs "
                "an external RAM and an instruction port (external ROM "
                "or icache)"
            )
        )
    if (
        memory.has_icache
        and generics is not None
        and "has_zifencei" in generics
        and not generics["has_zifencei"]
    ):
        problems.append(
            _problem(
                f"region {code[0]} is executable in the RAM behind an "
                "icache, which needs Zifencei in the profile"
            )
        )
    return problems


def _host_problems(
    memory: Memory,
    platform: dict[str, Any],
    ram: tuple[str, int, int] | None,
) -> list[Mismatch]:
    """Check the words the host shares behind a cache (V10).

    Parameters
    ----------
    memory : Memory
        The choice.
    platform : dict of {str: Any}
        The loaded platform.
    ram : tuple of (str, int, int) or None
        The RAM region, when named.

    Returns
    -------
    list of Mismatch
        A cache needs `reserved.fromhost`, in the last page of the RAM,
        which the cache bypasses.
    """
    if not (memory.has_icache or memory.has_dcache):
        return []
    reserved = platform_dict(platform, "reserved")
    if "fromhost" not in reserved:
        return [
            _problem(
                "a cache needs reserved.fromhost, the page it bypasses "
                "for the words the host writes"
            )
        ]
    if ram is None:
        return []
    last = (ram[1] + ram[2] - PAGE) // PAGE
    if evaluate(reserved["fromhost"]["base"]) // PAGE != last:
        return [
            _problem(
                "reserved.fromhost is not in the last 4 KiB page of the "
                f"RAM {ram[0]}, the page a cache bypasses"
            )
        ]
    return []


def _legacy_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Reject the old external flags of `generate.vhdl` beside `memory`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        One per `rom_external` or `ram_external` found.
    """
    vhdl = cast(
        dict[str, Any], platform_dict(platform, "generate").get("vhdl") or {}
    )
    return [
        _problem(
            f"generate.vhdl.{key} cannot sit beside memory, which derives it"
        )
        for key in ("rom_external", "ram_external")
        if key in vhdl
    ]


def problems(
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None = None,
) -> list[Mismatch]:
    """Check the memory choice against the map and the profile.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}, optional
        The generics of the profile, to check Zifencei; without them
        that check is skipped.

    Returns
    -------
    list of Mismatch
        Empty when the platform has no `memory` or it is valid.
    """
    memory, found = read(platform)
    if memory is None or found:
        return found
    rom = _region_span(platform, "rom")
    ram = _region_span(platform, "ram")
    return (
        _legacy_problems(platform)
        + _cache_problems(memory, rom, ram)
        + _exec_problems(memory, platform, generics)
        + _host_problems(memory, platform, ram)
    )


def notes(platform: dict[str, Any]) -> list[str]:
    """List the remarks the choice deserves, which are not errors.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of str
        A cache over an internal memory (it only adds latency and
        blocks, since the memory answers without wait), and the path
        that peripherals need in every combination.
    """
    memory = resolve(platform)
    if memory is None:
        return []
    out = [
        f"{name} over an internal {what}: it answers without wait, so "
        "the cache only adds latency on a miss and memory blocks"
        for name, what, over in (
            ("icache", "ROM", memory.has_icache and not memory.rom_external),
            ("dcache", "RAM", memory.has_dcache and not memory.ram_external),
        )
        if over
    ]
    if platform_list(platform, "peripherals"):
        out.append(
            "peripherals need the external bus path to the "
            "interconnect in every combination"
        )
    return out


def addr_width_names(platform: dict[str, Any]) -> list[str]:
    """Name the memories whose address width the simulation receives.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of str
        `config.addr_widths` when the platform lists it; otherwise,
        with a `memory` choice, the boot memory and each internal memory
        (an external one is a chip that the top sizes by itself);
        otherwise empty.
    """
    listed = platform_dict(platform, "config").get("addr_widths")
    if listed is not None:
        return [str(name) for name in listed]
    memory = resolve(platform)
    if memory is None:
        return []
    return ["boot_memory"] + [
        name
        for name, external in (
            ("rom", memory.rom_external),
            ("ram", memory.ram_external),
        )
        if not external
    ]


def parameters(platform: dict[str, Any]) -> dict[str, str | bool]:
    """Name the generics of the simulation top that the choice fixes.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: str or bool}
        `ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`,
        `ICACHE_SIZE_BITS` and `DCACHE_SIZE_BITS`, and
        `CACHE_WINDOW_BITS` when the map needs a window wider than the
        default of the caches (64 MiB); empty without a `memory`.
    """
    memory = resolve(platform)
    if memory is None:
        return {}
    window = cache_window_bits(platform)
    wide = (
        {"CACHE_WINDOW_BITS": str(window)} if window > MIN_WINDOW_BITS else {}
    )
    return wide | {
        "ROM_EXTERNAL": memory.rom_external,
        "RAM_EXTERNAL": memory.ram_external,
        "HAS_ICACHE": memory.has_icache,
        "HAS_DCACHE": memory.has_dcache,
        "ICACHE_SIZE_BITS": str(memory.icache_size_bits),
        "DCACHE_SIZE_BITS": str(memory.dcache_size_bits),
    }


def externals(
    spec: dict[str, Any], memory: Memory | None
) -> tuple[bool | None, bool | None]:
    """Find whether the ROM and the RAM are external.

    Parameters
    ----------
    spec : dict of {str: Any}
        The `generate.vhdl` section, which may fix `rom_external` and
        `ram_external` when the platform has no `memory`.
    memory : Memory or None
        The memory choice, which takes over when there is one.

    Returns
    -------
    tuple of (bool or None, bool or None)
        The ROM and the RAM; None where nothing fixes the choice.
    """
    if memory is not None:
        return memory.rom_external, memory.ram_external
    rom = spec.get("rom_external")
    ram = spec.get("ram_external")
    return (
        None if rom is None else bool(rom),
        None if ram is None else bool(ram),
    )


def vhdl_lines(memory: Memory, window: int = MIN_WINDOW_BITS) -> str:
    """Write the VHDL constants of the caches and of the core port.

    Parameters
    ----------
    memory : Memory
        The choice.
    window : int, optional
        The width of the tag window (see `cache_window_bits`).

    Returns
    -------
    str
        `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS`,
        `DCACHE_SIZE_BITS`, `CACHE_WINDOW_BITS`, `ROM_VIA_PORT` and
        `RAM_VIA_PORT`, each with its comment.
    """
    rows = (
        (
            "Existe cache de instruções.",
            "HAS_ICACHE",
            "boolean",
            memory.has_icache,
        ),
        ("Existe cache de dados.", "HAS_DCACHE", "boolean", memory.has_dcache),
        (
            "Tamanho da cache de instruções, em bits (256 se não existe).",
            "ICACHE_SIZE_BITS",
            "positive",
            memory.icache_size_bits,
        ),
        (
            "Tamanho da cache de dados, em bits (256 se não existe).",
            "DCACHE_SIZE_BITS",
            "positive",
            memory.dcache_size_bits,
        ),
        (
            "Largura da janela de endereços das caches, em bits: a tag guarda "
            "os bits abaixo dela (26 é 64 MiB, 27 é 128 MiB).",
            "CACHE_WINDOW_BITS",
            "natural",
            window,
        ),
        (
            "A ROM é alcançada pela porta do núcleo (externa ou com cache).",
            "ROM_VIA_PORT",
            "boolean",
            "ROM_EXTERNAL or HAS_ICACHE",
        ),
        (
            "A RAM é alcançada pela porta do núcleo (externa ou com cache).",
            "RAM_VIA_PORT",
            "boolean",
            "RAM_EXTERNAL or HAS_DCACHE",
        ),
    )
    return "".join(
        f"\t-- {comment}\n"
        f"\tconstant {name:<19} : {kind:<8} := "
        f"{str(value).lower() if isinstance(value, bool) else value};\n"
        for comment, name, kind, value in rows
    )
