"""The memory layout of a platform, written in blocks.

The platform YAML describes the memories of the core in a `memory`
block with three fixed names, and its peripherals as a mapping by name:

```yaml
memory:
  boot:                  # executable, always at address 0
    base: 0x00000000
    size: 4K
  instructions:          # executable; one segment in this phase
    - type: emulated     # flash, sdram, sram, onchip or emulated
      base: 0x00001000
      size: 252K
      on_bus: true       # reached through the bus (true) or the port
      latency:           # the emulated memory only
        first: 24
        next: 4
      sector_bytes: 4096
      cache:             # present: the instruction cache exists
        size_bits: 32768
  data:                  # not executable; one segment in this phase
    - type: sdram
      base: 0x40000000
      size: 64M
      on_bus: true
      cache:
        size_bits: 32768
peripherals:             # the order is the order of `<NAME>_INDEX`
  UART:
    base: 0xC0000000
    size: 16
```

`type` says what the memory is: `flash` (a NOR chip), `sdram`, `sram`,
`onchip` (blocks of the FPGA) or `emulated` (blocks of the FPGA with the
latency of a chip). A type that is not `onchip` is outside the core and
so needs `on_bus: true`. `on_bus` is given in both segments or in none
(the choice then comes from `--memory`).

The rest of the Tools reads the lists `regions` (`BOOT_MEMORY`, `FLASH`,
`RAM`), the section `memory` of the four choices (`rom`, `ram`,
`icache`, `dcache`) and the list `peripherals`, so `normalize_layout`
derives them. The old keys are refused with the way to migrate.
"""

from typing import Any, cast

from riscv_tools.memory_map import groups

BOOT = "BOOT_MEMORY"
FLASH = "FLASH"
RAM = "RAM"
TYPES = ("flash", "sdram", "sram", "onchip", "emulated")
_DEVICE = {"flash": "nor", "sdram": "sdram", "sram": "sram"}
_OF_DEVICE = {value: key for key, value in _DEVICE.items()}
_SEGMENT_KEYS = (
    "type",
    "base",
    "size",
    "on_bus",
    "cache",
    "latency",
    "sector_bytes",
)
_SIDES = (("instructions", "rom", "icache"), ("data", "ram", "dcache"))
_OLD_MEMORY = ("rom", "ram", "icache", "dcache")
_MAX_SEGMENTS = 1


def _mapping(value: Any, what: str) -> dict[str, Any]:
    """Check that a value is a mapping.

    Parameters
    ----------
    value : Any
        The value.
    what : str
        What it is, for the message.

    Returns
    -------
    dict of {str: Any}
        The value.

    Raises
    ------
    ValueError
        If it is not a mapping.
    """
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a mapping")
    return cast("dict[str, Any]", value)


def _boot(raw: Any) -> dict[str, Any]:
    """Read `memory.boot`.

    Parameters
    ----------
    raw : Any
        The value.

    Returns
    -------
    dict of {str: Any}
        The region `BOOT_MEMORY`: `base`, `size`, read only and
        executable.

    Raises
    ------
    ValueError
        If it has other keys than `base` and `size`.
    """
    block = _mapping(raw, "memory.boot")
    for old in ("kind", "exec"):
        if old in block:
            raise ValueError(
                f"memory.boot.{old} no longer exists: boot and "
                "instructions are executable and data is not"
            )
    extra = sorted(set(block) - {"base", "size"})
    if extra or len(block) != len(("base", "size")):
        raise ValueError("memory.boot takes exactly base and size")
    return {"name": BOOT, **block, "kind": "rom", "exec": True}


def _check_keys(seg: dict[str, Any], where: str) -> None:
    """Check the keys of a segment.

    Parameters
    ----------
    seg : dict of {str: Any}
        The segment.
    where : str
        `memory.instructions` or `memory.data`, for the message.

    Raises
    ------
    ValueError
        If the segment has an old key (`kind`, `exec`, `external`,
        `backend`, `device`), an unknown key or lacks `type`, `base` or
        `size`.
    """
    for old in ("kind", "exec", "external", "backend", "device"):
        if old in seg:
            raise ValueError(
                f"{where}.{old} no longer exists: use `type` and `on_bus`"
            )
    extra = sorted(str(key) for key in seg if key not in _SEGMENT_KEYS)
    if extra:
        raise ValueError(f"{where} has unknown keys {extra}")
    missing = [key for key in ("type", "base", "size") if key not in seg]
    if missing:
        raise ValueError(f"{where}.{missing[0]} is required")


def _segment(raw: Any, side: str) -> dict[str, Any]:
    """Read the one segment of `instructions` or `data`.

    Parameters
    ----------
    raw : Any
        The list of segments.
    side : str
        `instructions` or `data`.

    Returns
    -------
    dict of {str: Any}
        The segment.

    Raises
    ------
    ValueError
        If the list does not have exactly one segment, or the segment
        lacks `type`, `base` or `size`, has an unknown key or a type
        that does not exist.
    """
    where = f"memory.{side}"
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list of segments")
    items = cast("list[Any]", raw)
    if len(items) > _MAX_SEGMENTS:
        raise ValueError(f"{where}: vários segmentos ainda não são suportados")
    if not items:
        raise ValueError(f"{where} needs one segment")
    seg = _mapping(items[0], f"{where}[0]")
    _check_keys(seg, where)
    if seg["type"] not in TYPES:
        raise ValueError(
            f"{where}.type {seg['type']!r} must be one of {list(TYPES)}"
        )
    return seg


def _side(seg: dict[str, Any], where: str) -> dict[str, Any]:
    """Write the four-choice entry (`rom` or `ram`) of a segment.

    Parameters
    ----------
    seg : dict of {str: Any}
        The segment.
    where : str
        `memory.instructions` or `memory.data`, for the message.

    Returns
    -------
    dict of {str: Any}
        `external` and, by `type`, `backend` and `device`, with the
        `latency` and `sector_bytes` the segment has.

    Raises
    ------
    ValueError
        If a type outside the core is not on the bus.
    """
    kind = seg["type"]
    if kind != "onchip" and seg.get("on_bus") is not True:
        raise ValueError(f"{where}: type {kind} needs on_bus: true")
    entry: dict[str, Any] = {"external": seg["on_bus"]}
    if kind == "emulated":
        entry["backend"] = "emulado"
    elif kind in _DEVICE:
        entry |= {"backend": "dispositivo", "device": _DEVICE[kind]}
    for key in ("latency", "sector_bytes"):
        if key in seg:
            entry[key] = seg[key]
    return entry


def _declared(segments: list[dict[str, Any]]) -> bool:
    """Say whether the platform declares the memory choice.

    Parameters
    ----------
    segments : list of dict of {str: Any}
        The segment of `instructions` and the one of `data`.

    Returns
    -------
    bool
        False when neither segment gives `on_bus` or a `cache`.

    Raises
    ------
    ValueError
        If only one segment gives `on_bus`, or a type outside the core
        comes without it.
    """
    given = ["on_bus" in seg for seg in segments]
    if not any(given) and not any("cache" in seg for seg in segments):
        if any(seg["type"] != "onchip" for seg in segments):
            raise ValueError("a type outside the core needs on_bus: true")
        return False
    if not all(given):
        raise ValueError("on_bus is given in both segments or in none")
    return True


def _memory(segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Write the section `memory` of the four choices.

    Parameters
    ----------
    segments : list of dict of {str: Any}
        The segment of `instructions` and the one of `data`.

    Returns
    -------
    dict of {str: Any} or None
        `rom`, `ram`, `icache` and `dcache`; None when neither segment
        gives `on_bus` or a `cache` (the choice is left out).

    Raises
    ------
    ValueError
        If only one segment gives `on_bus`, or a segment is outside the
        core without it.
    """
    if not _declared(segments):
        return None
    out: dict[str, Any] = {}
    for seg, (side, old, cache) in zip(segments, _SIDES, strict=True):
        out[old] = _side(seg, f"memory.{side}")
        have = seg.get("cache")
        if have is None:
            out[cache] = {"enabled": False}
        else:
            block = _mapping(have, f"memory.{side}.cache")
            out[cache] = {"enabled": True, **block}
    return out


def _gpio_roles(where: str, value: dict[str, Any]) -> list[str]:
    """Read `role` or `roles` of a block of the GPIO.

    Parameters
    ----------
    where : str
        The path of the entry, for the messages.
    value : dict of {str: Any}
        The entry.

    Returns
    -------
    list of str
        The roles.

    Raises
    ------
    ValueError
        If both or none of `role` and `roles` are written, or a role
        cannot be a GPIO.
    """
    if ("role" in value) == ("roles" in value):
        raise ValueError(f"{where} needs exactly one of role and roles")
    raw = value["roles"] if "roles" in value else [value["role"]]
    listed = [str(role) for role in cast("list[Any]", raw)]
    bad = [role for role in listed if role not in groups.ROLES]
    if bad or not listed:
        raise ValueError(
            f"{where} role {bad or listed} must be one of {list(groups.ROLES)}"
        )
    return listed


def _block_roles(where: str, kind: str, value: dict[str, Any]) -> list[str]:
    """Read the roles of a block of groups.

    Parameters
    ----------
    where : str
        The path of the entry, for the messages.
    kind : str
        `gpio` or `seg_display`.
    value : dict of {str: Any}
        The entry.

    Returns
    -------
    list of str
        `role` or `roles`; `display` for a `seg_display`.

    Raises
    ------
    ValueError
        If the roles are missing, unknown or both written.
    """
    if kind == "seg_display":
        if "roles" in value or value.get("role", "display") != "display":
            raise ValueError(f"{where} shows only the role display")
        return ["display"]
    return _gpio_roles(where, value)


def _peripheral(name: str, value: dict[str, Any]) -> dict[str, Any]:
    """Read one entry of `peripherals`.

    Parameters
    ----------
    name : str
        The key of the entry.
    value : dict of {str: Any}
        The entry.

    Returns
    -------
    dict of {str: Any}
        The entry with its `name`; a block of groups (`kind`) has
        `roles` as a list and no `size`.

    Raises
    ------
    ValueError
        If a block of groups is not well formed.
    """
    if "kind" not in value:
        return {"name": name, **value}
    where = f"peripherals.{name}"
    kind = value["kind"]
    if kind not in groups.KINDS:
        raise ValueError(f"{where}.kind must be one of {list(groups.KINDS)}")
    extra = sorted(set(value) - {"kind", "role", "roles", "base", "groups"})
    if "size" in value:
        raise ValueError(
            f"{where}.size is derived from the groups (64 bytes each): "
            "do not write it"
        )
    if extra:
        raise ValueError(f"{where} has unknown keys {extra}")
    for key in ("base", "groups"):
        if key not in value:
            raise ValueError(f"{where}.{key} is required")
    return {
        "name": name,
        "kind": kind,
        "roles": _block_roles(where, kind, value),
        "base": value["base"],
        "groups": value["groups"],
    }


def _peripherals(raw: Any) -> list[dict[str, Any]]:
    """Turn the mapping of peripherals into the list the Tools read.

    Parameters
    ----------
    raw : Any
        The value of `peripherals`: a mapping by name, in file order.

    Returns
    -------
    list of dict of {str: Any}
        One entry per peripheral, with `name`, `base` and `size`, in the
        order of the file, which is the order of `<NAME>_INDEX`.

    Raises
    ------
    ValueError
        If `peripherals` is a list (the old form) or an entry is not a
        mapping.
    """
    if raw is None or raw == []:
        return []
    if isinstance(raw, list):
        raise ValueError(
            "peripherals is no longer a list: write a mapping by name, "
            "`UART:` with `base:` and `size:` below it, in the order of "
            "the indexes"
        )
    block = _mapping(raw, "peripherals")
    return [
        _peripheral(str(name), _mapping(value, f"peripherals.{name}"))
        for name, value in block.items()
    ]


def normalize_layout(data: dict[str, Any]) -> None:
    """Derive `regions`, `memory` and `peripherals` for the Tools.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform as read, changed in place.

    Raises
    ------
    ValueError
        If the platform has the old `regions` list or the old four
        choices in `memory`, or a block is not valid.
    """
    if "regions" in data:
        raise ValueError(
            "regions is no longer accepted: write the memory block with "
            "`boot`, `instructions` and `data` (BOOT_MEMORY, FLASH and "
            "RAM become those three; `kind` and `exec` are gone)"
        )
    if "peripherals" in data:
        data["peripherals"] = _peripherals(data["peripherals"])
    if "memory" not in data:
        return
    block = _mapping(data["memory"], "memory")
    old = [key for key in _OLD_MEMORY if key in block]
    if old:
        raise ValueError(
            f"memory.{old[0]} is no longer accepted: rom becomes the "
            "segment of `instructions`, ram the one of `data`, `external` "
            "becomes `on_bus`, backend and device become `type`, and "
            "icache and dcache become `cache` of the segment"
        )
    unknown = sorted(set(block) - {"boot", "instructions", "data"})
    if unknown or len(block) != len(("boot", "instructions", "data")):
        raise ValueError("memory takes boot, instructions and data")
    boot = _boot(block["boot"])
    inst = _segment(block["instructions"], "instructions")
    data_seg = _segment(block["data"], "data")
    data["regions"] = [
        boot,
        {"name": FLASH, **_region(inst), "kind": "rom", "exec": True},
        {"name": RAM, **_region(data_seg), "kind": "ram"},
    ]
    choice = _memory([inst, data_seg])
    if choice is None:
        del data["memory"]
    else:
        data["memory"] = choice


def _region(seg: dict[str, Any]) -> dict[str, Any]:
    """Give the `base` and `size` of a segment."""
    return {"base": seg["base"], "size": seg["size"]}


def _segment_of(
    region: dict[str, Any], entry: dict[str, Any] | None, cache: Any
) -> dict[str, Any]:
    """Write a segment from a region and its four-choice entries.

    Parameters
    ----------
    region : dict of {str: Any}
        The region.
    entry : dict of {str: Any} or None
        The `rom` or `ram` entry; None without a `memory` choice.
    cache : Any
        The `icache` or `dcache` entry, or None.

    Returns
    -------
    dict of {str: Any}
        The segment.
    """
    seg: dict[str, Any] = {"type": "onchip"}
    seg |= {"base": region["base"], "size": region["size"]}
    if entry is None:
        return seg
    device = entry.get("device")
    if entry.get("backend") == "emulado":
        seg["type"] = "emulated"
    elif device in _OF_DEVICE:
        seg["type"] = _OF_DEVICE[device]
    seg["on_bus"] = entry["external"]
    seg |= {k: entry[k] for k in ("latency", "sector_bytes") if k in entry}
    if cache and cache.get("enabled"):
        seg["cache"] = {"size_bits": cache["size_bits"]}
    return seg


def _memory_block(
    regions: list[dict[str, Any]], choice: Any
) -> dict[str, Any]:
    """Write the `memory` block of a platform of the internal form.

    Parameters
    ----------
    regions : list of dict of {str: Any}
        The boot, FLASH and RAM regions, in that order.
    choice : Any
        The section of the four choices, or None.

    Returns
    -------
    dict of {str: Any}
        `boot`, `instructions` and `data`.
    """
    old = cast("dict[str, Any]", choice or {})
    boot = {"base": regions[0]["base"], "size": regions[0]["size"]}
    return {
        "boot": boot,
        "instructions": [
            _segment_of(regions[1], old.get("rom"), old.get("icache"))
        ],
        "data": [_segment_of(regions[2], old.get("ram"), old.get("dcache"))],
    }


def _written(entry: dict[str, Any]) -> dict[str, Any]:
    """Write one peripheral as the file has it.

    Parameters
    ----------
    entry : dict of {str: Any}
        The peripheral of the internal form.

    Returns
    -------
    dict of {str: Any}
        Without `name`; a block of groups also without the derived
        `size` and `plan`, and with `role` or `roles`.
    """
    out = {k: v for k, v in entry.items() if k != "name"}
    if "kind" not in entry:
        return out
    for key in ("size", "plan", "roles"):
        out.pop(key, None)
    roles = entry["roles"]
    if entry["kind"] == "gpio":
        out["role" if len(roles) == 1 else "roles"] = (
            roles[0] if len(roles) == 1 else roles
        )
    return out


def _peripheral_map(items: Any) -> dict[str, dict[str, Any]]:
    """Write the list of peripherals as a mapping by name.

    Parameters
    ----------
    items : Any
        The list, in the internal form.

    Returns
    -------
    dict of {str: dict of {str: Any}}
        The entries without `name`, in the order of the list.
    """
    return {
        str(p["name"]): _written(p)
        for p in cast("list[dict[str, Any]]", items)
    }


def to_layout(platform: dict[str, Any]) -> dict[str, Any]:
    """Write a platform of the internal form in the block form.

    Parameters
    ----------
    platform : dict of {str: Any}
        A platform with the list `regions` (boot, FLASH and RAM, in
        that order), the optional section `memory` of the four choices
        and the list `peripherals`.

    Returns
    -------
    dict of {str: Any}
        A copy with `memory` in blocks and `peripherals` as a mapping.
    """
    out = {k: v for k, v in platform.items() if k != "regions"}
    regions = cast("list[dict[str, Any]]", platform.get("regions") or [])
    if regions:
        out["memory"] = _memory_block(regions, platform.get("memory"))
    if "peripherals" in out:
        out["peripherals"] = _peripheral_map(out["peripherals"])
    return out
