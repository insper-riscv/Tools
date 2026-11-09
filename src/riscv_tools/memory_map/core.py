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

NUM_REGS = {"i": 32, "e": 16}
DEFAULT_ADDRESS_BITS = 32
MIN_ADDRESS_BITS = 16
MAX_ADDRESS_BITS = 64


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


def periph_window_base(bits: int) -> int:
    """Name the base of the peripheral window of an address width.

    Parameters
    ----------
    bits : int
        The width of the physical address.

    Returns
    -------
    int
        The upper half of the address space, `1 << (bits - 1)`
        (`0x80000000` for 32 bits).
    """
    return 1 << (bits - 1)


def periph_id_shift(bits: int) -> int:
    """Name the bit where the identifier of a peripheral starts.

    Parameters
    ----------
    bits : int
        The width of the physical address.

    Returns
    -------
    int
        `bits - 4`: the identifier takes the three bits below the
        window bit (28 for 32 bits).
    """
    return bits - 4


def periph_window(platform: dict[str, Any]) -> int:
    """Find the base of the peripheral window of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `periph_window` fixes the base, which
        otherwise is derived from `address_bits`.

    Returns
    -------
    int
        The base address of the window.
    """
    if "periph_window" in platform:
        return evaluate(platform["periph_window"])
    return periph_window_base(address_bits(platform))


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


def _choice(has_base: bool, has_offset: bool) -> str:
    """Say whether an entry gives exactly one of `base` and `offset`.

    Parameters
    ----------
    has_base : bool
        The entry has `base`.
    has_offset : bool
        The entry has `offset`.

    Returns
    -------
    str
        `ok` for exactly one, `both` or `none` otherwise.
    """
    if has_base != has_offset:
        return "ok"
    return "both" if has_base else "none"


def _complete(raw: dict[str, Any], window: int, bits: int) -> dict[str, Any]:
    """Complete one peripheral with its `base`, `offset` and `id`.

    Parameters
    ----------
    raw : dict of {str: Any}
        The entry as written.
    window : int
        The base of the peripheral window.
    bits : int
        The width of the physical address.

    Returns
    -------
    dict of {str: Any}
        A copy with `choice`, `relative` and, when the entry gives
        exactly one of `base` and `offset`, both of them and the `id`.
    """
    item = dict(raw)
    item["relative"] = "offset" in raw or "padding" in raw
    item["choice"] = _choice("base" in raw, "offset" in raw)
    if item["choice"] != "ok":
        return item
    if "offset" in raw:
        offset = evaluate(raw["offset"])
        base = window + offset
    else:
        base = evaluate(raw["base"])
        offset = base - window
    item |= {"base": base, "offset": offset}
    if "id" not in raw and offset >= 0:
        item["id"] = offset >> periph_id_shift(bits)
    return item


def peripheral_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the peripherals, each with a `base` and an `offset`.

    A peripheral gives exactly one of `base` (absolute) and `offset`
    (from the base of the peripheral window), and `id` is optional.
    Every entry comes back with both `base` and `offset` and, when it
    can be derived, `id` (`offset >> (address_bits - 4)`). An entry
    that gives neither or both of `base` and `offset` comes back as
    written, for the validation to report. `choice` is `ok`, `both` or
    `none`, and `relative` is true when the entry uses `offset` or
    `padding`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of dict of {str: Any}
        A copy of each entry of `peripherals`, completed.
    """
    try:
        bits = address_bits(platform)
    except ValueError:
        bits = DEFAULT_ADDRESS_BITS
    window = periph_window({**platform, "address_bits": bits})
    return [
        _complete(raw, window, bits)
        for raw in platform_list(platform, "peripherals")
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
    for periph in peripheral_list(platform):
        out[f"{periph['name']}.base"] = evaluate(periph["base"])
        out[f"{periph['name']}.offset"] = int(periph["offset"])
        out[f"{periph['name']}.id"] = int(periph["id"])
    return out
