"""Check the consistency of a memory map before any copy is read."""

from typing import Any, cast

from riscv_tools.memory_map import memory
from riscv_tools.memory_map.core import (
    DEFAULT_ADDRESS_BITS,
    Mismatch,
    address_bits,
    peripheral_list,
    platform_dict,
    platform_list,
    strict_periph,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.profile import (
    RV32_XLEN,
    profile_name,
    xlen_of,
)

LEGACY_FIELDS = ("id", "offset", "padding")


def hex_text(value: int) -> str:
    """Format an integer as hexadecimal, keeping the sign in front.

    Parameters
    ----------
    value : int
        The number.

    Returns
    -------
    str
        `0x1F`, or `-0x8` for a negative value.
    """
    return f"-0x{-value:X}" if value < 0 else f"0x{value:X}"


def span(base: int, size: int) -> str:
    """Format an address range for messages.

    Parameters
    ----------
    base : int
        First address.
    size : int
        Length in bytes.

    Returns
    -------
    str
        `0xBASE-0xEND`.
    """
    return f"0x{base:X}-0x{base + size:X}"


def overlaps(label: str, spans: list[tuple[str, int, int]]) -> list[Mismatch]:
    """Find pairs of ranges that overlap.

    Parameters
    ----------
    label : str
        What the ranges are, for the message (`regions`, `reserved`).
    spans : list of tuple of (str, int, int)
        `(name, base, size)` of each range.

    Returns
    -------
    list of Mismatch
        One per overlapping pair.
    """
    return [
        Mismatch("platform", "", f"{label} {name_a} and {name_b} overlap")
        for i, (name_a, base_a, size_a) in enumerate(spans)
        for name_b, base_b, size_b in spans[i + 1 :]
        if base_a < base_b + size_b and base_b < base_a + size_a
    ]


def _boot_problems(
    boot: dict[str, Any],
    spans: list[tuple[str, int, int]],
    execs: list[tuple[str, int, int]],
) -> list[Mismatch]:
    """Check the boot entry points against the regions.

    Parameters
    ----------
    boot : dict of {str: Any}
        The platform's `boot` section.
    spans : list of tuple of (str, int, int)
        Every region, in declaration order (the first is the boot
        memory).
    execs : list of tuple of (str, int, int)
        The executable regions.

    Returns
    -------
    list of Mismatch
        `entry` outside every executable region, `wait_restart` outside
        the first region.
    """
    problems: list[Mismatch] = []
    if "entry" in boot and not any(
        b <= evaluate(boot["entry"]) < b + s for _, b, s in execs
    ):
        problems.append(
            Mismatch(
                "platform", "", "boot.entry is not inside an executable region"
            )
        )
    if "wait_restart" in boot and spans:
        name, base, size = spans[0]
        if not base <= evaluate(boot["wait_restart"]) < base + size:
            problems.append(
                Mismatch(
                    "platform", "", f"boot.wait_restart is not inside {name}"
                )
            )
    return problems


def _bits(platform: dict[str, Any]) -> tuple[int, list[Mismatch]]:
    """Read the address width.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    tuple of (int, list of Mismatch)
        The width (the default when `address_bits` is invalid) and the
        V-A1 problem, if any.
    """
    try:
        return address_bits(platform), []
    except ValueError as error:
        return DEFAULT_ADDRESS_BITS, [
            Mismatch("platform", "", f"V-A1 {error}")
        ]


def _removed_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Refuse the keys that the free peripheral addresses removed.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        One per `periph_window` at the top and per `ext_base` or
        `periph_base` in `generate.vhdl`: the core no longer knows an
        external or peripheral window.
    """
    vhdl = cast(
        dict[str, Any], platform_dict(platform, "generate").get("vhdl") or {}
    )
    found = [("periph_window", platform)] + [
        (f"generate.vhdl.{key}", vhdl) for key in ("ext_base", "periph_base")
    ]
    return [
        Mismatch(
            "platform",
            "",
            f"V-P6 {name.rsplit('.', 1)[-1]} is no longer accepted: the "
            "core does not know the peripheral window; give each "
            "peripheral its `base` and `size`",
        )
        for name, where in found
        if name.rsplit(".", 1)[-1] in where
    ]


def _core_map_problems(platform: dict[str, Any], bits: int) -> list[Mismatch]:
    """Check the order of the regions of the core (V-M1 to V-M5).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `config` or `generate.vhdl` names the FLASH
        and the RAM in `rom` and `ram`.
    bits : int
        The width of the physical address.

    Returns
    -------
    list of Mismatch
        The BOOT_MEMORY (the first region) must start at 0, end at or
        before the FLASH, which has a positive size and ends at or
        before the RAM, which has a positive size and fits the address
        space. Empty when the platform names neither the FLASH nor the
        RAM.
    """
    flash = memory.region_span(platform, "rom")
    ram = memory.region_span(platform, "ram")
    regions = platform_list(platform, "regions")
    if flash is None or ram is None or not regions:
        return []
    boot = evaluate(regions[0]["base"]), evaluate(regions[0]["size"])
    checks = [
        ("V-M1", "the BOOT_MEMORY must start at address 0", boot[0] == 0),
        (
            "V-M2",
            f"the BOOT_MEMORY must end before the FLASH {flash[0]}",
            sum(boot) <= flash[1],
        ),
        ("V-M3", f"the FLASH {flash[0]} needs a positive size", flash[2] > 0),
        (
            "V-M4",
            f"the FLASH {flash[0]} must end before the RAM {ram[0]}",
            flash[1] + flash[2] <= ram[1],
        ),
        (
            "V-M5",
            f"the RAM {ram[0]} needs a positive size and must fit "
            f"2**{bits} bytes",
            ram[2] > 0 and ram[1] + ram[2] <= 1 << bits,
        ),
    ]
    return [
        Mismatch("platform", "", f"{code} {text}")
        for code, text, ok in checks
        if not ok
    ]


def validate_platform(
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None = None,
    xlen: int | None = None,
) -> list[Mismatch]:
    """Check the map's own consistency, before any copy is read.

    Regions must not overlap; reserved words must sit inside a RAM
    region and not overlap each other; the boot entry must be inside an
    executable region and `wait_restart` inside the first one; every
    peripheral must have an aligned window that overlaps neither another
    peripheral nor a region (see `_peripheral_problems`); the three
    regions the core knows must be in order (see `_core_map_problems`);
    the width `address_bits` must satisfy V-A1 to V-A6 (see
    `_address_problems`); and the `memory` choice, when there is one,
    must be well formed and fit the map (see `memory.problems`).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}, optional
        The generics of the profile, to check Zifencei under an
        instruction cache and the access faults of V-A5; without them
        those checks are skipped.
    xlen : int, optional
        The register width of V-A2 and V-A5, in place of the one of the
        profile of the platform.

    Returns
    -------
    list of Mismatch
        The problems; empty when the map is consistent.
    """
    regions = platform_list(platform, "regions")
    spans = [
        (r["name"], evaluate(r["base"]), evaluate(r["size"])) for r in regions
    ]
    rams = [
        s
        for s, r in zip(spans, regions, strict=True)
        if r.get("kind") == "ram"
    ]
    reserved = [
        (n, evaluate(v["base"]), evaluate(v["size"]))
        for n, v in platform_dict(platform, "reserved").items()
    ]
    execs = [s for s, r in zip(spans, regions, strict=True) if r.get("exec")]
    bits, problems = _bits(platform)
    problems += overlaps("regions", spans) + overlaps("reserved", reserved)
    problems += [
        Mismatch(
            "platform",
            "",
            f"reserved {name} ({span(base, size)}) is not inside a RAM region",
        )
        for name, base, size in reserved
        if not any(b <= base and base + size <= b + s for _, b, s in rams)
    ]
    problems += _boot_problems(platform_dict(platform, "boot"), spans, execs)
    problems += _address_problems(platform, bits, spans, generics, xlen)
    problems += memory.problems(platform)
    problems += _strict_problems(platform) + _removed_problems(platform)
    problems += _core_map_problems(platform, bits)
    return problems + _peripheral_problems(
        platform_list(platform, "peripherals"), spans, bits
    )


def _strict_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check that `strict_periph`, when given, is a boolean (V-S1).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        One problem when the key is not a boolean; else empty.
    """
    try:
        strict_periph(platform)
    except ValueError as error:
        return [Mismatch("platform", "", f"V-S1 {error}")]
    return []


def _xlen(platform: dict[str, Any], xlen: int | None) -> int:
    """Find the register width a width check compares against.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    xlen : int or None
        The width given by the caller.

    Returns
    -------
    int
        `xlen` when given, else the one of the profile; 32 when the
        profile name is not valid (the profile checks report that).
    """
    if xlen is not None:
        return xlen
    try:
        return xlen_of(platform)
    except ValueError:
        return RV32_XLEN


def _boot_address_problems(boot: dict[str, Any], bits: int) -> list[Mismatch]:
    """Check that the boot addresses are inside the space (V-A6).

    Parameters
    ----------
    boot : dict of {str: Any}
        The platform's `boot` section.
    bits : int
        The width of the physical address.

    Returns
    -------
    list of Mismatch
        One per `entry` or `wait_restart` at or above `2**bits`.
    """
    return [
        Mismatch(
            "platform",
            "",
            f"V-A6 boot.{key} 0x{evaluate(boot[key]):X} is outside the "
            f"address space of address_bits {bits} (2**{bits} = "
            f"0x{1 << bits:X})",
        )
        for key in ("entry", "wait_restart")
        if key in boot and evaluate(boot[key]) >= 1 << bits
    ]


def _address_problems(
    platform: dict[str, Any],
    bits: int,
    spans: list[tuple[str, int, int]],
    generics: dict[str, bool | int] | None,
    xlen: int | None,
) -> list[Mismatch]:
    """Check the width of the address against the rest (V-A2 to V-A6).

    V-A1 (the field is an integer from 16 to 64) is checked when the
    field is read, and V-A4 (the peripheral window) with the regions and
    the peripherals.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    bits : int
        The width of the physical address.
    spans : list of tuple of (str, int, int)
        Every region, as `(name, base, size)`.
    generics : dict of {str: bool or int} or None
        The generics of the profile; without them V-A5 is skipped.
    xlen : int or None
        The register width, or None to read it off the profile.

    Returns
    -------
    list of Mismatch
        V-A2 (above `xlen` bits), V-A3 (a region
        beyond `2**bits` bytes), V-A5 (a width below `xlen` needs the
        access faults) and V-A6 (a boot address beyond `2**bits`).
    """
    width = _xlen(platform, xlen)
    problems: list[Mismatch] = []
    if bits > width:
        problems.append(
            Mismatch(
                "platform",
                "",
                f"V-A2 address_bits {bits} is above XLEN {width} of the "
                f"core (type {width}, profile {profile_name(platform)}): "
                "ADDR_BITS maior que XLEN",
            )
        )
    problems += [
        Mismatch(
            "platform",
            "",
            f"V-A3 region {name} ({span(base, size)}) does not fit "
            f"address_bits {bits} (2**{bits} = 0x{1 << bits:X} bytes)",
        )
        for name, base, size in spans
        if base + size > 1 << bits
    ]
    if (
        generics is not None
        and bits < width
        and not generics.get("has_access_faults")
    ):
        problems.append(
            Mismatch(
                "platform",
                "",
                f"V-A5 address_bits {bits} is below xlen {width} but the "
                "profile lacks has_access_faults (the AccessFaults "
                "extra), which an access above the window needs to "
                "raise an access fault",
            )
        )
    return problems + _boot_address_problems(
        platform_dict(platform, "boot"), bits
    )


def _legacy_problems(raw: dict[str, Any]) -> list[Mismatch]:
    """Refuse the fields that the window derived from `size` replaced.

    Parameters
    ----------
    raw : dict of {str: Any}
        One entry of `peripherals`, as written.

    Returns
    -------
    list of Mismatch
        One per `id`, `offset` and `padding`, with the migration: the
        entry gives its absolute `base` (`id: 5` becomes
        `base: 0xD0000000`) and the `size` in bytes of its registers.
    """
    return [
        Mismatch(
            "platform",
            "",
            f"V-P1 peripheral {raw.get('name')}: `{key}` is no longer "
            "accepted; give `base` (the absolute address, aligned to the "
            "window, so `id: 5` becomes `base: 0xD0000000`) and `size` "
            "(the bytes of registers)",
        )
        for key in LEGACY_FIELDS
        if key in raw
    ]


def _window_problems(item: dict[str, Any], bits: int) -> list[Mismatch]:
    """Check the size, the alignment and the room of one peripheral.

    Parameters
    ----------
    item : dict of {str: Any}
        A peripheral completed by `peripheral_list`, with `base` and
        `size`.
    bits : int
        The width of the physical address.

    Returns
    -------
    list of Mismatch
        V-P1 for a size that is not positive, V-P2 for a base that is
        not a multiple of the window and V-A4 for a window that goes
        past `2**bits`.
    """
    name, base, size = item["name"], int(item["base"]), int(item["size"])
    if size <= 0:
        return [
            Mismatch(
                "platform",
                "",
                f"V-P1 peripheral {name}: `size` must be positive",
            )
        ]
    window = int(item["window"])
    found: list[Mismatch] = []
    if base % window:
        found.append(
            Mismatch(
                "platform",
                "",
                f"V-P2 peripheral {name} base 0x{base:X} is not aligned "
                f"to its window of 0x{window:X} bytes (size 0x{size:X})",
            )
        )
    if base + window > 1 << bits:
        found.append(
            Mismatch(
                "platform",
                "",
                f"V-A4 peripheral {name} window ({span(base, window)}) "
                f"does not fit address_bits {bits}",
            )
        )
    return found


def _peripheral_problems(
    peripherals: list[dict[str, Any]],
    spans: list[tuple[str, int, int]],
    bits: int,
) -> list[Mismatch]:
    """Check the peripherals against the address space and the regions.

    Each entry gives `base` and `size` and none of the removed fields
    (V-P1), its base is aligned to its window (V-P2), no two windows
    overlap (V-P4), no window overlaps a region (V-P5) and the window is
    inside the address space (V-A4).

    Parameters
    ----------
    peripherals : list of dict of {str: Any}
        The `peripherals` section, as written.
    spans : list of tuple of (str, int, int)
        Every region, as `(name, base, size)`.
    bits : int
        The width of the physical address.

    Returns
    -------
    list of Mismatch
        The problems; empty when the peripherals are consistent.
    """
    problems: list[Mismatch] = []
    windows: list[tuple[str, int, int]] = []
    for raw in peripherals:
        problems += _legacy_problems(raw)
        missing = [key for key in ("base", "size") if key not in raw]
        if missing:
            problems.append(
                Mismatch(
                    "platform",
                    "",
                    f"V-P1 peripheral {raw.get('name')}: `base` and `size` "
                    f"are needed, `{missing[0]}` is missing",
                )
            )
            continue
        item = _completed(raw)
        problems += _window_problems(item, bits)
        if "window" in item:
            windows.append(
                (str(item["name"]), int(item["base"]), int(item["window"]))
            )
    problems += _overlap_problems(windows, windows, "V-P4 peripherals", True)
    return problems + _overlap_problems(
        windows, spans, "V-P5 peripheral", False
    )


def _completed(raw: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the numbers of one entry and derive its window.

    Parameters
    ----------
    raw : dict of {str: Any}
        An entry of `peripherals` that has `base` and `size`.

    Returns
    -------
    dict of {str: Any}
        The entry with `base`, `size` and `window` (when `size` is
        positive) as numbers.
    """
    return peripheral_list({"peripherals": [raw]})[0]


def _overlap_problems(
    first: list[tuple[str, int, int]],
    second: list[tuple[str, int, int]],
    label: str,
    same: bool,
) -> list[Mismatch]:
    """Find windows that take the same bytes as a window or a region.

    Parameters
    ----------
    first : list of tuple of (str, int, int)
        `(name, base, size)` of each peripheral window.
    second : list of tuple of (str, int, int)
        The windows (`same`) or the regions to compare with.
    label : str
        The start of the message, with the code of the rule.
    same : bool
        The two lists are one, so each pair counts once.

    Returns
    -------
    list of Mismatch
        One per overlapping pair.
    """
    found: list[Mismatch] = []
    for i, (name_a, base_a, size_a) in enumerate(first):
        for name_b, base_b, size_b in second[i + 1 :] if same else second:
            if base_a < base_b + size_b and base_b < base_a + size_a:
                found.append(
                    Mismatch(
                        "platform",
                        "",
                        f"{label} {name_a} and {name_b} overlap: "
                        f"{span(base_a, size_a)} and "
                        f"{span(base_b, size_b)}",
                    )
                )
    return found
