"""Read a pins file and expand the signal groups the board names."""

import re
from typing import Any, cast

from riscv_tools.board_schema.fields import Section, raise_if
from riscv_tools.board_schema.model import Pin

DIRECTIONS = ("in", "out", "inout")
CONFIRMATIONS = ("manual", "repo", "inferred")
_BUS = re.compile(r"^(\w+)\[(\d+):(\d+)\]$")
_BUS_2D = re.compile(r"^(\w+)\[(\d+):(\d+)\]\[(\d+):(\d+)\]$")


def _span(high: str, low: str) -> range:
    """Give the indices of a range written `[high:low]`.

    Parameters
    ----------
    high : str
        The first index.
    low : str
        The last index.

    Returns
    -------
    range
        The indices in ascending order.
    """
    first, last = sorted((int(high), int(low)))
    return range(first, last + 1)


def expand_group(spec: str) -> list[str]:
    """List the signals of a group written as a board names it.

    A group is a signal (`CLOCK_50`, `KEY[0]`), a bus (`LEDR[9:0]`,
    which is `LEDR[0]` to `LEDR[9]`) or a bus of buses
    (`HEX[5:0][6:0]`, which is `HEX0[0]` to `HEX5[6]`, a bus per
    digit).

    Parameters
    ----------
    spec : str
        The group.

    Returns
    -------
    list of str
        The signals, in ascending order.
    """
    flat = _BUS_2D.match(spec)
    if flat is not None:
        base, hi_a, lo_a, hi_b, lo_b = flat.groups()
        return [
            f"{base}{i}[{j}]"
            for i in _span(hi_a, lo_a)
            for j in _span(hi_b, lo_b)
        ]
    bus = _BUS.match(spec)
    if bus is not None:
        base, high, low = bus.groups()
        return [f"{base}[{i}]" for i in _span(high, low)]
    return [spec]


def group_count(spec: str) -> int:
    """Count the units of a group: the bits of a bus or the digits.

    Parameters
    ----------
    spec : str
        The group, as `expand_group` reads it.

    Returns
    -------
    int
        The width of the first index; 1 for a single signal.
    """
    flat = _BUS_2D.match(spec)
    if flat is not None:
        return len(_span(flat.group(2), flat.group(3)))
    bus = _BUS.match(spec)
    if bus is not None:
        return len(_span(bus.group(2), bus.group(3)))
    return 1


def conflict_pins(raw: Any) -> set[str]:
    """List the pins a pins file declares as shared by several signals.

    Parameters
    ----------
    raw : Any
        The parsed pins file.

    Returns
    -------
    set of str
        The pins of `conflicts`; empty when there are none.
    """
    if not isinstance(raw, dict):
        return set()
    listed = cast("dict[str, Any]", raw).get("conflicts")
    if not isinstance(listed, list):
        return set()
    return {
        str(cast("dict[str, Any]", item).get("pin"))
        for item in cast("list[Any]", listed)
        if isinstance(item, dict)
    }


def parse_pins(raw: Any, label: str = "pins") -> list[Pin]:
    """Read a pins file, checking every signal.

    Parameters
    ----------
    raw : Any
        The parsed YAML.
    label : str, optional
        The name used in the messages.

    Returns
    -------
    list of Pin
        The signals, in file order.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section(label, raw, problems)
    top.text("board")
    top.text("device")
    top.get("notes")
    top.get("conflicts")
    found: list[Pin] = []
    listed = top.items("signals")
    for index, item in enumerate(listed):
        entry = Section(f"{label}.signals[{index}]", item, problems)
        name = entry.text("name")
        pin = entry.text("pin")
        standard = entry.text("io_standard")
        direction = entry.text("direction", choices=DIRECTIONS)
        entry.text("source", required=False)
        confirmed = entry.text("confirmed", choices=CONFIRMATIONS)
        entry.text("note", required=False)
        entry.done()
        if name and pin and standard and direction and confirmed:
            found.append(Pin(name, pin, standard, direction, confirmed))
    if not listed:
        problems.append(f"{label}.signals must name at least one signal")
    top.done()
    raise_if(problems)
    return found
