"""Assemble the selection environment from the real host.

This is the only place where the identification reads the host: the
board packages, the inventory, `jtagconfig`, and the USB ports. The
global options `--board`, `--board-id` and `--cable` of the command
line (or `RISCV_TOOLS_BOARD`, `RISCV_TOOLS_BOARD_ID` and
`RISCV_TOOLS_CABLE`, which a lock passes to the command it runs) are
kept here as the override of a run.
"""

import os
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.board.errors import BoardError
from riscv_tools.board.inventory import load_inventory
from riscv_tools.board.select import (
    AUTO,
    Environment,
    Request,
    Selection,
    select_board,
)
from riscv_tools.board.usb import port_path
from riscv_tools.board_schema import Board, Catalog, SchemaError
from riscv_tools.jtag.hardware import read_cables

BOARDS_ENV = "RISCV_TOOLS_BOARDS"
_override: dict[str, str | None] = {}


def set_override(
    board: str | None, board_id: str | None, cable: str | None
) -> None:
    """Keep the global selection options of the command line.

    Parameters
    ----------
    board, board_id, cable : str or None
        `--board`, `--board-id` and `--cable`.
    """
    _override.clear()
    _override.update(board=board, board_id=board_id, cable=cable)


def override_request() -> Request:
    """Return the selection options of this run.

    Returns
    -------
    Request
        The command line first, then the environment.
    """

    def pick(key: str, env: str) -> str | None:
        return _override.get(key) or os.environ.get(env) or None

    return Request(
        cable=pick("cable", "RISCV_TOOLS_CABLE"),
        board_id=pick("board_id", "RISCV_TOOLS_BOARD_ID"),
        board=pick("board", "RISCV_TOOLS_BOARD"),
    )


def boards_directories(explicit: list[str], root: Path) -> list[Path]:
    """List the `boards/` folders of the catalog to read.

    Parameters
    ----------
    explicit : list of str
        The `--boards-dir` options.
    root : Path
        The project root.

    Returns
    -------
    list of Path
        The explicit ones, those of `RISCV_TOOLS_BOARDS`, then the
        `boards/` folder of the catalog at the root and at
        `<root>/Insper-RISC-V`.
    """
    env = [p for p in os.environ.get(BOARDS_ENV, "").split(os.pathsep) if p]
    return [Path(p) for p in [*explicit, *env]] + [
        Catalog.for_root(root).boards,
        Catalog.for_root(root / "Insper-RISC-V").boards,
    ]


def load_boards(directories: list[Path]) -> dict[str, Board]:
    """Read every board of the catalogs in the folders.

    Parameters
    ----------
    directories : list of Path
        `boards/` folders; a missing one is skipped, and a board found
        twice keeps the first.

    Returns
    -------
    dict of {str: Board}
        The boards by identifier, sorted by it.

    Raises
    ------
    BoardError
        A `board.yaml` does not follow the schema.
    """
    found: dict[str, Board] = {}
    for directory in directories:
        catalog = Catalog(directory, directory)
        for name in catalog.board_names():
            try:
                found.setdefault(name, catalog.load_board(name))
            except SchemaError as error:
                raise BoardError(f"board {name}: {error}") from error
    return dict(sorted(found.items()))


def platform_choice(path: Path | None) -> tuple[str | None, tuple[str, ...]]:
    """Read the `board` and `boards` fields of a platform.yaml.

    Parameters
    ----------
    path : Path or None
        The platform file.

    Returns
    -------
    tuple of (str or None, tuple of str)
        The `board:` value and the list of boards `auto` may take.
    """
    if path is None:
        return None, ()
    doc = cast(
        dict[str, Any],
        yaml.safe_load(path.read_text(encoding="utf-8")) or {},
    )
    board = doc.get("board")
    allowed = doc.get("boards") or ()
    return (None if board is None else str(board)), tuple(
        str(b) for b in allowed
    )


def build_environment(
    directories: list[Path],
    inventory: Path | None = None,
    host: str | None = None,
) -> Environment:
    """Read the host and build the environment of the selection.

    Parameters
    ----------
    directories : list of Path
        The `boards/` folders of the catalog.
    inventory : Path, optional
        The inventory file in place of the default.
    host : str, optional
        The label of the host.

    Returns
    -------
    Environment
        The boards, the inventory, the cables and the ports.
    """
    return Environment(
        load_boards(directories),
        load_inventory(inventory, host),
        read_cables(),
        port_path,
    )


def select_for_config(cfg: dict[str, Any], root: Path) -> Selection:
    """Select the board of a project config, for the JTAG link.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged config; uses `quartus.board` and `quartus.boards`.
    root : Path
        The project root.

    Returns
    -------
    Selection
        The selected board.
    """
    quartus = cfg["quartus"]
    request = override_request()
    env = build_environment(boards_directories([], root))
    return select_board(
        env,
        Request(
            cable=request.cable,
            board_id=request.board_id,
            board=request.board,
            platform_board=quartus.get("board") or AUTO,
            allowed=tuple(quartus.get("boards") or ()),
        ),
    )
