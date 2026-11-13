"""Check the catalog of boards, families and chips by itself.

Independent of any platform: every file follows its schema, every board
names a family and chips that exist, and every signal a board cites is a
signal of its pins file. A pin shared by two signals must be listed in
the `conflicts` of the pins file.
"""

from collections import defaultdict

from riscv_tools.board_schema import (
    Board,
    Catalog,
    NotFoundError,
    Pin,
    SchemaError,
    VideoMode,
    expand_group,
)


def _cited(board: Board) -> list[tuple[str, str]]:
    """List the signals a board cites, with where it cites them.

    Parameters
    ----------
    board : Board
        The board.

    Returns
    -------
    list of tuple of (str, str)
        The signal and the field that names it; the prefixes of the
        memories are given with a trailing underscore.
    """
    cited = [
        (c.signal, f"clocks.inputs {c.name}") for c in board.clocks.inputs
    ]
    cited.append((board.clocks.reset_signal, "clocks.reset"))
    for role, entry in board.io.items():
        cited += [(s, f"io.{role}") for s in expand_group(entry.signals)]
    if board.video is not None:
        cited.append((f"{board.video.signals}_", "io.video"))
    cited += [(signal, "console.uart") for signal in board.console.uart]
    for kind, memory in board.memories.items():
        cited += [(f"{p}_", f"memories.{kind}") for p in memory.signals]
    return cited


def _pin_problems(
    board: Board, pins: list[Pin], allowed: set[str]
) -> list[str]:
    """Check the signals of a board against its pins file.

    Parameters
    ----------
    board : Board
        The board.
    pins : list of Pin
        Its signals.
    allowed : set of str
        The pins the pins file lists in `conflicts`.

    Returns
    -------
    list of str
        One problem for each cited signal that does not exist, and for
        each pin used twice outside `conflicts`.
    """
    names = {pin.name for pin in pins}
    problems = [
        f"board {board.board}: {where} cites {name}, which is not in pins"
        for name, where in _cited(board)
        if not (
            any(n.startswith(name) for n in names)
            if name.endswith("_")
            else name in names
        )
    ]
    by_pin: dict[str, list[str]] = defaultdict(list)
    for pin in pins:
        by_pin[pin.pin].append(pin.name)
    problems += [
        f"board {board.board}: pin {number} is used by "
        f"{', '.join(users)} and is not in conflicts"
        for number, users in by_pin.items()
        if len(users) > 1 and number not in allowed
    ]
    return problems


def _mode_problems(board: Board, modes: dict[str, VideoMode]) -> list[str]:
    """Check that the modes a board lists are in the catalog of modes.

    Parameters
    ----------
    board : Board
        The board.
    modes : dict of str to VideoMode
        The catalog of video modes.

    Returns
    -------
    list of str
        One problem for each listed mode the catalog lacks.
    """
    if board.video is None:
        return []
    return [
        f"board {board.board}: io.video.modes cites {mode}, which is not "
        f"in video-modes.yaml"
        for mode in board.video.modes
        if mode not in modes
    ]


def _check_board(
    catalog: Catalog, name: str, modes: dict[str, VideoMode]
) -> list[str]:
    """Check one board and everything it names.

    Parameters
    ----------
    catalog : Catalog
        The catalog.
    name : str
        The board.
    modes : dict of str to VideoMode
        The catalog of video modes.

    Returns
    -------
    list of str
        The problems.
    """
    try:
        board = catalog.load_board(name)
        problems: list[str] = []
        if board.family not in catalog.family_names():
            problems.append(f"board {name}: family {board.family} not found")
        problems += [
            f"board {name}: chip {m.chip} not found"
            for m in board.memories.values()
            if m.chip and m.chip not in catalog.chip_names()
        ]
        pins = catalog.load_pins(name, board)
        conflicts = catalog.load_conflicts(name, board)
    except (SchemaError, NotFoundError) as bad:
        if isinstance(bad, SchemaError):
            return list(bad.problems)
        return [str(bad)]
    return (
        problems
        + _mode_problems(board, modes)
        + _pin_problems(board, pins, conflicts)
    )


def check_catalog(catalog: Catalog) -> list[str]:
    """Check every family, chip and board of the catalog.

    Parameters
    ----------
    catalog : Catalog
        The catalog.

    Returns
    -------
    list of str
        The problems; empty when the catalog is consistent.
    """
    problems: list[str] = []
    for family in catalog.family_names():
        try:
            catalog.load_family(family)
        except SchemaError as bad:
            problems += bad.problems
    for chip in catalog.chip_names():
        try:
            catalog.load_chip(chip)
        except SchemaError as bad:
            problems += bad.problems
    modes: dict[str, VideoMode] = {}
    try:
        modes = catalog.load_video_modes()
    except SchemaError as bad:
        problems += bad.problems
    for board in catalog.board_names():
        problems += _check_board(catalog, board, modes)
    return problems
