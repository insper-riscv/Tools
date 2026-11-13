"""The groups of the GPIO and of the seven-segment display blocks.

A peripheral of `kind: gpio` (or `seg_display`) is a block that
gathers the pins of one or more roles of the board (`leds`,
`switches`, `keys`, `display`) into groups, and each group has its
own register file:

```yaml
peripherals:
  LEDR:
    kind: gpio
    role: leds
    base: 0x80002000
    groups: solo             # one group per pin
  KEY:
    kind: gpio
    role: keys
    base: 0x80004000
    groups: [[0, 1], [2, 3]] # two groups of two pins
  HEX:
    kind: seg_display
    base: 0x80005000
    groups: [[0, 1, 2, 3], [4, 5]]
```

`groups` is a list of lists of pin indexes or one of `solo` (a group
per pin), `all` (one group with every pin), `pairs` and `trios` (groups
of 2 or 3 consecutive pins, the last one may be smaller). A pin that is
in no group is off. The pins of a role are numbered from 0, and with
`roles: [a, b]` the pins of `b` follow the ones of `a`. A group has at
most 32 pins, a block takes 64 bytes for each group and `size` is not
written: the window is derived from the number of groups.

The number of pins of each role and their polarity come from the
`board.yaml` of each board in `boards`, so the platform is checked
against every board it lists (rules G-1 to G-7).
"""

import re
from pathlib import Path
from typing import Any, cast

import yaml

KINDS = ("gpio", "seg_display")
ROLES = (
    "leds",
    "switches",
    "keys",
    "display",
    "leds_green",
    "gpio",
    "ex_io",
    "hsmc",
)
SHORTCUTS = ("solo", "all", "pairs", "trios")
GROUP_BYTES = 64
MAX_GROUP_PINS = 32
SEGMENTS = 7
_STEP = {"pairs": 2, "trios": 3}
_BUS = re.compile(r"\[(\d+):(\d+)\]")
# Direção fixa do pino por papel: 2 saída, 1 entrada, 0 livre.
_DIRECTION = {
    "leds": 2,
    "leds_green": 2,
    "display": 2,
    "switches": 1,
    "keys": 1,
    "gpio": 0,
    "ex_io": 0,
    "hsmc": 0,
}


def block_size(group_count: int) -> int:
    """Give the bytes of registers of a block of groups.

    Parameters
    ----------
    group_count : int
        The number of groups.

    Returns
    -------
    int
        64 bytes for each group.
    """
    return GROUP_BYTES * group_count


def _shortcut(spec: str, count: int) -> list[list[int]] | None:
    """Write the groups of a shortcut.

    Parameters
    ----------
    spec : str
        `solo`, `all`, `pairs` or `trios`.
    count : int
        The number of pins.

    Returns
    -------
    list of list of int or None
        The groups; None when `spec` is not a shortcut.
    """
    if spec == "solo":
        return [[pin] for pin in range(count)]
    if spec == "all":
        return [list(range(count))] if count else []
    if spec not in _STEP:
        return None
    step = _STEP[spec]
    return [
        list(range(i, min(i + step, count))) for i in range(0, count, step)
    ]


def _is_pin_lists(spec: Any) -> bool:
    """Say whether a value is a list of lists of pin indexes.

    Parameters
    ----------
    spec : Any
        The value.

    Returns
    -------
    bool
        True for a list whose items are lists of integers.
    """
    if not isinstance(spec, list):
        return False
    return all(
        isinstance(group, list)
        and all(
            isinstance(pin, int) and not isinstance(pin, bool)
            for pin in cast("list[Any]", group)
        )
        for group in cast("list[Any]", spec)
    )


def expand(spec: Any, count: int) -> list[list[int]]:
    """Write the groups a `groups` value stands for.

    Parameters
    ----------
    spec : Any
        A shortcut or a list of lists of pin indexes.
    count : int
        The number of pins of the roles of the block.

    Returns
    -------
    list of list of int
        The groups, in order.

    Raises
    ------
    ValueError
        If the value is neither a shortcut nor a list of lists of
        integers.
    """
    if isinstance(spec, str):
        shortcut = _shortcut(spec, count)
        if shortcut is not None:
            return shortcut
    elif _is_pin_lists(spec):
        return [list(cast("list[int]", g)) for g in cast("list[Any]", spec)]
    raise ValueError(
        f"groups must be one of {list(SHORTCUTS)} or a list of lists of "
        "pin indexes"
    )


def _size_problems(name: str, groups: list[list[int]]) -> list[str]:
    """Report the groups that are empty or too big (G-3)."""
    return [
        f"G-3 peripheral {name} group {index} has {len(group)} pins, "
        f"from 1 to {MAX_GROUP_PINS} are allowed"
        for index, group in enumerate(groups)
        if not group or len(group) > MAX_GROUP_PINS
    ]


def _range_problems(name: str, pins: list[int], count: int) -> list[str]:
    """Report the pins at or above the number of pins (G-1)."""
    return [
        f"G-1 peripheral {name} pin {pin} is out of range: the board "
        f"has {count} pins in the roles"
        for pin in pins
        if pin < 0 or pin >= count
    ]


def _repeat_problems(name: str, pins: list[int]) -> list[str]:
    """Report the pins that are listed more than once (G-2)."""
    return [
        f"G-2 peripheral {name} repeats pin {pin}"
        for pin in sorted({p for p in pins if pins.count(p) > 1})
    ]


def problems(name: str, groups: list[list[int]], count: int) -> list[str]:
    """Check the groups of a block against the pins of a board.

    Parameters
    ----------
    name : str
        The peripheral, for the messages.
    groups : list of list of int
        The groups.
    count : int
        The number of pins the board gives the roles of the block.

    Returns
    -------
    list of str
        G-1 (an index at or above `count`), G-2 (a repeated pin), G-3
        (an empty group or one with more than 32 pins).
    """
    pins = [pin for group in groups for pin in group]
    return (
        _size_problems(name, groups)
        + _range_problems(name, pins, count)
        + _repeat_problems(name, pins)
    )


def off_pins(groups: list[list[int]], count: int) -> list[int]:
    """List the pins that no group has.

    Parameters
    ----------
    groups : list of list of int
        The groups.
    count : int
        The number of pins.

    Returns
    -------
    list of int
        The off pins, in order.
    """
    used = {pin for group in groups for pin in group}
    return [pin for pin in range(count) if pin not in used]


def find_catalog(platform_file: Path) -> Path | None:
    """Find the `boards/` folder above a platform file.

    Parameters
    ----------
    platform_file : Path
        The platform YAML.

    Returns
    -------
    Path or None
        The nearest `boards` folder that has a `families` folder, going
        up from the file; None when there is none.
    """
    for folder in platform_file.resolve().parents:
        if (folder / "boards" / "families").is_dir():
            return folder / "boards"
    return None


def _span_count(spec: str) -> int:
    """Count the units of one group of signals.

    Parameters
    ----------
    spec : str
        A signal (`CLOCK_50`) or a bus (`LEDR[9:0]`).

    Returns
    -------
    int
        The width of the first index; 1 for a single signal.
    """
    found = _BUS.search(spec)
    return abs(int(found[1]) - int(found[2])) + 1 if found else 1


def role_pins(catalog: Path, board: str) -> dict[str, tuple[int, str]]:
    """Read the pins of each role of a board.

    Parameters
    ----------
    catalog : Path
        The `boards/` folder.
    board : str
        The board.

    Returns
    -------
    dict of {str: tuple of (int, str)}
        For each role of the `io` of the `board.yaml`, the number of
        pins (for `display`, the number of digits) and the polarity,
        `high` or `low`.

    Raises
    ------
    ValueError
        If the board file is missing.
    """
    path = catalog / board / "board.yaml"
    if not path.is_file():
        raise ValueError(f"board {board!r} has no board.yaml in {catalog}")
    data = cast("dict[str, Any]", yaml.safe_load(path.read_text()) or {})
    out: dict[str, tuple[int, str]] = {}
    for role, entry in cast("dict[str, Any]", data.get("io") or {}).items():
        fields = cast("dict[str, Any]", entry)
        specs = fields.get("signals", "")
        listed = cast(
            "list[Any]", specs if isinstance(specs, list) else [specs]
        )
        count = sum(_span_count(str(spec)) for spec in listed)
        out[str(role)] = (count, str(fields.get("active", "high")))
    return out


def _role_list(entry: dict[str, Any]) -> list[str]:
    """Name the roles a block gathers.

    Parameters
    ----------
    entry : dict of {str: Any}
        A peripheral of the internal form.

    Returns
    -------
    list of str
        `roles`, or `display` for a `seg_display`.
    """
    if entry["kind"] == "seg_display":
        return ["display"]
    return [str(role) for role in entry.get("roles", [])]


def _pins(
    entry: dict[str, Any], io: dict[str, tuple[int, str]], board: str
) -> tuple[list[tuple[int, bool]], list[str]]:
    """List the pins of the roles of a block on one board.

    Parameters
    ----------
    entry : dict of {str: Any}
        A peripheral of the internal form.
    io : dict of {str: tuple of (int, str)}
        The pins of each role of the board.
    board : str
        The board, for the messages.

    Returns
    -------
    tuple of (list of tuple of (int, bool), list of str)
        For each pin the direction code (`1` input, `2` output) and
        whether it is active low, then the problems (G-4: the board
        lacks a role).
    """
    pins: list[tuple[int, bool]] = []
    found: list[str] = []
    for role in _role_list(entry):
        if role not in io:
            found.append(
                f"G-4 peripheral {entry['name']}: board {board} has no "
                f"role {role}"
            )
            continue
        count, active = io[role]
        if role == "display" and entry["kind"] == "gpio":
            count *= SEGMENTS
        pins += [(_DIRECTION[role], active == "low")] * count
    return pins, found


def _plan(
    entry: dict[str, Any], io: dict[str, tuple[int, str]], board: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Work out the groups and the pin attributes of a block on a board.

    Parameters
    ----------
    entry : dict of {str: Any}
        A peripheral of the internal form.
    io : dict of {str: tuple of (int, str)}
        The pins of each role of the board.
    board : str
        The board.

    Returns
    -------
    tuple of (dict or None, list of str)
        The plan (`groups`, `off`, `dirs`, `active_low`; for a
        `seg_display` the pins are the digits) or None when the board
        lacks a role or the groups do not hold, and the problems.
    """
    pins, found = _pins(entry, io, board)
    if found:
        return None, found
    try:
        groups = expand(entry["groups"], len(pins))
    except ValueError as error:
        return None, [f"G-5 peripheral {entry['name']}: {error}"]
    found = problems(str(entry["name"]), groups, len(pins))
    if found:
        return None, found
    plan = {
        "groups": groups,
        "off": off_pins(groups, len(pins)),
        "dirs": [direction for direction, _ in pins],
        "active_low": [low for _, low in pins],
        "pins": len(pins),
    }
    return plan, []


def _sized(entry: dict[str, Any], plans: dict[str, Any]) -> list[str]:
    """Derive the `size` of a block from its plans.

    Parameters
    ----------
    entry : dict of {str: Any}
        A peripheral of the internal form, changed in place.
    plans : dict of {str: Any}
        The plan of each board.

    Returns
    -------
    list of str
        G-6 when the boards give a different number of groups.
    """
    counts = {len(plan["groups"]) for plan in plans.values()}
    if len(counts) > 1:
        return [
            f"G-6 peripheral {entry['name']} has a different number of "
            f"groups on each board ({sorted(counts)}), so its window "
            "would differ"
        ]
    if counts:
        entry["size"] = block_size(counts.pop())
    return []


def _fallback(entry: dict[str, Any]) -> list[str]:
    """Size a block without a board: only when the groups are written.

    Parameters
    ----------
    entry : dict of {str: Any}
        A peripheral of the internal form, changed in place.

    Returns
    -------
    list of str
        G-0 when the number of groups needs the pins of a board.
    """
    spec = entry["groups"]
    if isinstance(spec, list):
        entry["size"] = block_size(len(cast("list[Any]", spec)))
        return []
    entry["size"] = block_size(1)
    if spec == "all":
        return []
    return [
        f"G-0 peripheral {entry['name']}: `groups: {spec}` needs the pins "
        "of the board, so `boards` and the catalog of boards are needed"
    ]


def _required(
    data: dict[str, Any], entries: list[dict[str, Any]], board: str
) -> list[str]:
    """Warn of a required role whose pins are all off.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform: `io` gives the `need` of each role.
    entries : list of dict of {str: Any}
        The blocks, with their plans.
    board : str
        The board.

    Returns
    -------
    list of str
        One warning per required role that no block uses on the board.
    """
    io = cast("dict[str, Any]", data.get("io") or {})
    used = {
        role
        for entry in entries
        if board in entry.get("plan", {})
        and len(entry["plan"][board]["groups"]) > 0
        for role in _role_list(entry)
    }
    return [
        f"warning: role {role} is required by `io` but every pin of it "
        f"is off on board {board}"
        for role, fields in io.items()
        if isinstance(fields, dict)
        and cast("dict[str, Any]", fields).get("need") == "required"
        and entries
        and role not in used
        and any(role in _role_list(entry) for entry in entries)
    ]


def _on_boards(
    data: dict[str, Any],
    entries: list[dict[str, Any]],
    boards: list[str],
    catalog: Path,
) -> tuple[list[str], list[str]]:
    """Plan the blocks on each board of the platform.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform.
    entries : list of dict of {str: Any}
        The blocks, changed in place (`plan` and `size`).
    boards : list of str
        The boards of the platform.
    catalog : Path
        The `boards/` folder.

    Returns
    -------
    tuple of (list of str, list of str)
        The problems and the notes.
    """
    found: list[str] = []
    notes: list[str] = []
    for board in boards:
        io = role_pins(catalog, board)
        for entry in entries:
            plan, bad = _plan(entry, io, board)
            found += bad
            if plan is not None:
                entry["plan"][board] = plan
                notes += _off_notes(entry, plan, board)
        notes += _required(data, entries, board)
    for entry in entries:
        found += _sized(entry, entry["plan"])
        entry.setdefault("size", block_size(1))
    return found, notes


def _blocks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """List the peripherals that are blocks of groups.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform.

    Returns
    -------
    list of dict of {str: Any}
        The peripherals with a `kind`, in order.
    """
    items = cast("list[dict[str, Any]]", data.get("peripherals") or [])
    return [item for item in items if item.get("kind")]


def _unplanned(entries: list[dict[str, Any]]) -> list[str]:
    """Size the blocks without a board and collect the problems.

    Parameters
    ----------
    entries : list of dict of {str: Any}
        The blocks, changed in place.

    Returns
    -------
    list of str
        The G-0 problems.
    """
    return [text for entry in entries for text in _fallback(entry)]


def resolve(data: dict[str, Any], platform_file: Path) -> None:
    """Resolve the groups of the blocks against the boards.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform with `peripherals` in the internal form; each
        block gets its `size` and its `plan` (by board), and the
        platform gets `_group_problems` and `_group_notes`.
    platform_file : Path
        The platform YAML, which locates the catalog of boards.
    """
    entries = _blocks(data)
    if not entries:
        return
    boards = [str(b) for b in cast("list[Any]", data.get("boards") or [])]
    catalog = find_catalog(platform_file)
    for entry in entries:
        entry["plan"] = {}
    if boards and catalog is not None:
        found, notes = _on_boards(data, entries, boards, catalog)
    else:
        found, notes = _unplanned(entries), []
    data["_group_problems"] = found
    data["_group_notes"] = notes


def _off_notes(
    entry: dict[str, Any], plan: dict[str, Any], board: str
) -> list[str]:
    """Say which pins of a block are off on a board.

    Parameters
    ----------
    entry : dict of {str: Any}
        The block.
    plan : dict of {str: Any}
        Its plan on the board.
    board : str
        The board.

    Returns
    -------
    list of str
        One note when some pin is in no group; else empty.
    """
    if not plan["off"]:
        return []
    return [
        f"peripheral {entry['name']}: pins {plan['off']} are off on "
        f"board {board}"
    ]
