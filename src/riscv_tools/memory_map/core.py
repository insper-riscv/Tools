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

PERIPHERAL_ID_SHIFT = 28


PERIPHERAL_WINDOW_BASE = 0x80000000


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
