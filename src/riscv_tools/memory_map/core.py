"""Verify a platform's memory map against every copy written by hand.

One YAML file is the source of truth for the map (region bases and
sizes, the words reserved at the top of RAM, the boot entry points, the
peripheral windows) and lists, under `checks`, where each copy lives
and how to read the number out of it.

A check names a `file` (relative to the project root), reads one value
out of it (a regular expression with one capture group, or a dotted
`yaml` path) and compares it with an `expect` expression over the map's
symbols. A check whose pattern matches nothing fails.

Symbols are `<REGION>.base|size|end|words`, `<reserved>.base|size|end`,
`boot.entry`, `boot.wait_restart` and `<PERIPHERAL>.base|id`.
Expressions accept `+ - * /` (exact division only), `log2()` (exact),
`clog2()` (rounded up), and hexadecimal, decimal, VHDL-based
(`16#800#`) and suffixed (`30K`, `0x800u`) numbers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.memory_map.expressions import evaluate

_PERIPHERAL_ID_SHIFT = 28


_PERIPHERAL_WINDOW_BASE = 0x80000000


@dataclass(frozen=True)
class Mismatch:
    """One disagreement (or unreadable copy) found by the check.

    Parameters
    ----------
    check : str
        The check's name, or `platform` for a problem in the map itself.
    file : str
        The file the value was read from ("" for the map itself).
    detail : str
        What disagrees: actual and expected values, or why it could not
        be read.
    """

    check: str
    file: str
    detail: str

    def __str__(self) -> str:
        """Format the mismatch as one line for the command's report.

        Returns
        -------
        str
            `check (file): detail`.
        """
        where = f" ({self.file})" if self.file else ""
        return f"{self.check}{where}: {self.detail}"


def load_platform(path: Path) -> dict[str, Any]:
    """Read a platform's YAML file.

    Parameters
    ----------
    path : Path
        The platform file.

    Returns
    -------
    dict of {str: Any}
        The parsed map and checks.

    Raises
    ------
    ValueError
        If the file is not a mapping.
    """
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    return cast(dict[str, Any], data)


def platform_list(platform: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Read a section of the platform that is a list of mappings.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        The section (`regions`, `peripherals`, `checks`).

    Returns
    -------
    list of dict of {str: Any}
        The section; empty when absent.
    """
    return cast(list[dict[str, Any]], platform.get(key) or [])


def platform_dict(platform: dict[str, Any], key: str) -> dict[str, Any]:
    """Read a section of the platform that is a mapping.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        The section (`reserved`, `boot`).

    Returns
    -------
    dict of {str: Any}
        The section; empty when absent.
    """
    return cast(dict[str, Any], platform.get(key) or {})


def symbols(platform: dict[str, Any]) -> dict[str, int]:
    """Flatten a platform's map into the symbols checks can name.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: int}
        `REGION.base|size|end|words`, `reserved.base|size|end`,
        `boot.entry|wait_restart`, `PERIPHERAL.base|id`.
    """
    out: dict[str, int] = {}
    for region in platform_list(platform, "regions"):
        base = evaluate(region["base"])
        size = evaluate(region["size"])
        name = region["name"]
        out |= {
            f"{name}.base": base,
            f"{name}.size": size,
            f"{name}.end": base + size,
            f"{name}.words": size // 4,
        }
    for name, item in platform_dict(platform, "reserved").items():
        base = evaluate(item["base"])
        size = evaluate(item["size"])
        out |= {
            f"{name}.base": base,
            f"{name}.size": size,
            f"{name}.end": base + size,
        }
    for key, value in (platform_dict(platform, "boot")).items():
        out[f"boot.{key}"] = evaluate(value)
    for periph in platform_list(platform, "peripherals"):
        out[f"{periph['name']}.base"] = evaluate(periph["base"])
        out[f"{periph['name']}.id"] = int(periph["id"])
    return out


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


def _span(base: int, size: int) -> str:
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


def _overlaps(label: str, spans: list[tuple[str, int, int]]) -> list[Mismatch]:
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
    problems = _overlaps("regions", spans) + _overlaps("reserved", reserved)
    problems += [
        Mismatch(
            "platform",
            "",
            f"reserved {name} ({_span(base, size)}) is not inside a RAM "
            "region",
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
        want = _PERIPHERAL_WINDOW_BASE | (
            int(periph["id"]) << _PERIPHERAL_ID_SHIFT
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
