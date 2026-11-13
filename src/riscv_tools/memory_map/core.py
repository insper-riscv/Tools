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
`boot.entry`, `boot.wait_restart` and
`<PERIPHERAL>.base|size|window|index`.
Expressions accept `+ - * /` (exact division only), `log2()` (exact),
`clog2()` (rounded up), and hexadecimal, decimal, VHDL-based
(`16#800#`) and suffixed (`30K`, `0x800u`) numbers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.memory_map.core_profile import normalize
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.profile import profile_replaced

NUM_REGS = {"i": 32, "e": 16}
DEFAULT_ADDRESS_BITS = 32
MIN_ADDRESS_BITS = 16
MAX_ADDRESS_BITS = 64
MIN_WINDOW = 16


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
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    platform = cast(dict[str, Any], data)
    normalize(platform, path, replaced=profile_replaced())
    return platform


def address_bits(platform: dict[str, Any]) -> int:
    """Read the width of the physical address of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `address_bits`, an integer from 16 to 64
        (32 when absent).

    Returns
    -------
    int
        The width in bits.

    Raises
    ------
    ValueError
        If the field is not an integer from 16 to 64.
    """
    value = platform.get("address_bits", DEFAULT_ADDRESS_BITS)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_ADDRESS_BITS <= value <= MAX_ADDRESS_BITS
    ):
        raise ValueError(
            f"address_bits must be an integer from {MIN_ADDRESS_BITS} to "
            f"{MAX_ADDRESS_BITS}, got {value!r}"
        )
    return value


def profile_base(platform: dict[str, Any]) -> str:
    """Read the base ISA letter of the platform's profile.

    The platform picks its profile in `profile:` (`rv32im`, `rv32em`,
    ...): `rv32` followed by the base letter, `i` for RV32I (32
    registers) or `e` for RV32E (16 registers).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        `i` or `e`; `i` when the platform names no profile.

    Raises
    ------
    ValueError
        If the profile does not start with `rv32i` or `rv32e`.
    """
    profile = str(platform.get("profile", "rv32i")).lower()
    if profile[:5] not in ("rv32i", "rv32e"):
        raise ValueError(f"profile {profile!r} must start with rv32i or rv32e")
    return profile[4]


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


def strict_periph(platform: dict[str, Any]) -> bool:
    """Read the `strict_periph` key of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        The value of the key; true when it is absent.

    Raises
    ------
    ValueError
        If the key is present and is not a boolean.
    """
    value = platform.get("strict_periph", True)
    if not isinstance(value, bool):
        raise ValueError(f"strict_periph must be true or false, not {value!r}")
    return value


def window_of(size: int) -> int:
    """Name the window of a peripheral, derived from its size.

    Parameters
    ----------
    size : int
        The bytes of registers of the peripheral.

    Returns
    -------
    int
        The smallest power of two that is not below `size`, and never
        below `MIN_WINDOW` (16 bytes).
    """
    return 1 << (max(size, MIN_WINDOW) - 1).bit_length()


def _complete(raw: dict[str, Any], index: int) -> dict[str, Any]:
    """Complete one peripheral with its numbers and its `window`.

    Parameters
    ----------
    raw : dict of {str: Any}
        The entry as written.
    index : int
        The position of the entry in `peripherals`.

    Returns
    -------
    dict of {str: Any}
        A copy with `index` and, for each of `base` and `size` that the
        entry gives, the evaluated number; `window` when `size` is
        positive. A field that is missing stays missing, for the
        validation to report.
    """
    item = dict(raw)
    item["index"] = index
    for key in ("base", "size"):
        if key in raw:
            item[key] = evaluate(raw[key])
    if int(item.get("size", 0)) > 0:
        item["window"] = window_of(int(item["size"]))
    return item


def peripheral_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the peripherals, each with its `base`, `size` and `window`.

    A peripheral gives its `base` (absolute, aligned to its window) and
    its `size` (bytes of registers). The window is derived: the
    smallest power of two that is not below `size`, with at least 16
    bytes. The `index` of a peripheral is its position in the list,
    which is also its position in the tables of the SoC.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of dict of {str: Any}
        A copy of each entry of `peripherals`, completed.
    """
    return [
        _complete(raw, index)
        for index, raw in enumerate(platform_list(platform, "peripherals"))
    ]


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
        `boot.entry|wait_restart`, `PERIPHERAL.base|size|window|index`.
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
    for periph in peripheral_list(platform):
        name = periph["name"]
        out[f"{name}.index"] = int(periph["index"])
        for key in ("base", "size", "window"):
            if key in periph:
                out[f"{name}.{key}"] = int(periph[key])
    return out
