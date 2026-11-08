"""Check the consistency of a memory map before any copy is read."""

from typing import Any

from riscv_tools.memory_map import memory
from riscv_tools.memory_map.core import (
    DEFAULT_ADDRESS_BITS,
    Mismatch,
    address_bits,
    periph_id_shift,
    periph_window,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.profile import (
    RV32_XLEN,
    RV64_XLEN,
    profile_name,
    xlen_of,
)


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


def _bits_and_window(
    platform: dict[str, Any],
) -> tuple[int, int, list[Mismatch]]:
    """Read the address width and the peripheral window.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    tuple of (int, int, list of Mismatch)
        The width (the default when `address_bits` is invalid), the
        base of the peripheral window and the V-A1 problem, if any.
    """
    try:
        return address_bits(platform), periph_window(platform), []
    except ValueError as error:
        fixed = {**platform, "address_bits": DEFAULT_ADDRESS_BITS}
        return (
            DEFAULT_ADDRESS_BITS,
            periph_window(fixed),
            [Mismatch("platform", "", f"V-A1 {error}")],
        )


def validate_platform(
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None = None,
    xlen: int | None = None,
) -> list[Mismatch]:
    """Check the map's own consistency, before any copy is read.

    Regions must not overlap; reserved words must sit inside a RAM
    region and not overlap each other; every region must end at or
    below the peripheral window (the upper half of the address space,
    `2**(address_bits - 1)`, unless `periph_window` fixes another
    base), since the lower half belongs to the BOOT_MEMORY, the ROM and
    the RAM and the upper half to the peripherals; the boot entry must
    be inside an executable region and `wait_restart` inside the first
    one; a peripheral's base must be the window base or-ed with
    `id << (address_bits - 4)` (the L2IP window convention); the width
    `address_bits` must satisfy V-A1 to V-A6 (see
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
    bits, window, problems = _bits_and_window(platform)
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
    problems += [
        Mismatch(
            "platform",
            "",
            f"region {name} ({span(base, size)}) is not below the "
            f"peripheral window 0x{window:X} (V-A4, address_bits {bits})",
        )
        for name, base, size in spans
        if base + size > window
    ]
    problems += _boot_problems(platform_dict(platform, "boot"), spans, execs)
    problems += _address_problems(platform, bits, spans, generics, xlen)
    problems += memory.problems(platform, generics)
    return problems + _peripheral_problems(
        platform_list(platform, "peripherals"), bits, window
    )


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
        V-A2 (above 32 bits needs an rv64 profile), V-A3 (a region
        beyond `2**bits` bytes), V-A5 (a width below `xlen` needs the
        access faults) and V-A6 (a boot address beyond `2**bits`).
    """
    width = _xlen(platform, xlen)
    problems: list[Mismatch] = []
    if bits > RV32_XLEN and width != RV64_XLEN:
        problems.append(
            Mismatch(
                "platform",
                "",
                f"V-A2 address_bits {bits} is above 32 but the profile "
                f"{profile_name(platform)} is not rv64",
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


def _peripheral_problems(
    peripherals: list[dict[str, Any]], bits: int, window: int
) -> list[Mismatch]:
    """Check the base of every peripheral against its id (V-A4).

    Parameters
    ----------
    peripherals : list of dict of {str: Any}
        The `peripherals` section.
    bits : int
        The width of the physical address.
    window : int
        The base of the peripheral window.

    Returns
    -------
    list of Mismatch
        One per peripheral whose base does not follow the convention,
        and one per peripheral whose `id << (address_bits - 4)` falls
        outside `2**address_bits`.
    """
    problems: list[Mismatch] = []
    shift = periph_id_shift(bits)
    for periph in peripherals:
        offset = int(periph["id"]) << shift
        want = window | offset
        if offset >= 1 << bits:
            problems.append(
                Mismatch(
                    "platform",
                    "",
                    f"V-A4 peripheral {periph['name']} id {periph['id']}: "
                    f"id << (address_bits - 4) = 0x{offset:X} is outside "
                    f"2**address_bits (address_bits {bits})",
                )
            )
        elif evaluate(periph["base"]) != want:
            problems.append(
                Mismatch(
                    "platform",
                    "",
                    f"peripheral {periph['name']} base is not 0x{want:X} "
                    f"(window bit set, id {periph['id']} at bit {shift})",
                )
            )
    return problems
