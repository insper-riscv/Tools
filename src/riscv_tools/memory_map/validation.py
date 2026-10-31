"""Check the consistency of a memory map before any copy is read."""

from typing import Any

from riscv_tools.memory_map.core import (
    PERIPHERAL_ID_SHIFT,
    PERIPHERAL_WINDOW_BASE,
    Mismatch,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate


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
        Every region, in declaration order (the first is the boot ROM).
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


def validate_platform(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the map's own consistency, before any copy is read.

    Regions must not overlap; reserved words must sit inside a RAM
    region and not overlap each other; the boot entry must be inside an
    executable region and `wait_restart` inside the first one; a
    peripheral's base must be `0x80000000 | id << 28` (the L2IP window
    convention).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

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
    problems = overlaps("regions", spans) + overlaps("reserved", reserved)
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
    return problems + _peripheral_problems(
        platform_list(platform, "peripherals")
    )


def _peripheral_problems(
    peripherals: list[dict[str, Any]],
) -> list[Mismatch]:
    """Check the base of every peripheral against its id.

    Parameters
    ----------
    peripherals : list of dict of {str: Any}
        The `peripherals` section.

    Returns
    -------
    list of Mismatch
        One per peripheral whose base does not follow the convention.
    """
    problems: list[Mismatch] = []
    for periph in peripherals:
        want = PERIPHERAL_WINDOW_BASE | (
            int(periph["id"]) << PERIPHERAL_ID_SHIFT
        )
        if evaluate(periph["base"]) != want:
            problems.append(
                Mismatch(
                    "platform",
                    "",
                    f"peripheral {periph['name']} base is not 0x{want:X} "
                    f"(bit31=1, id {periph['id']} in bits 30:28)",
                )
            )
    return problems
