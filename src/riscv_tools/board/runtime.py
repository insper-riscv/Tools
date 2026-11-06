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

from riscv_tools.board.inventory import load_inventory
from riscv_tools.board.select import (
    AUTO,
    Environment,
    Request,
    Selection,
    select_board,
)
from riscv_tools.board.spec import BoardSpec, adhoc_board, load_boards
from riscv_tools.board.usb import port_path
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
    """List where the board packages are looked for.

    Parameters
    ----------
    explicit : list of str
        The `--boards-dir` options.
    root : Path
        The project root.

    Returns
    -------
    list of Path
        The explicit ones, those of `RISCV_TOOLS_BOARDS`, then
        `<root>/boards` and `<root>/Insper-RISC-V/boards`.
    """
    env = [p for p in os.environ.get(BOARDS_ENV, "").split(os.pathsep) if p]
    chosen = [*explicit, *env]
    return [Path(p) for p in chosen] + [
        root / "boards",
        root / "Insper-RISC-V" / "boards",
    ]


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
    idcode: str | None = None,
) -> tuple[Environment, str | None]:
    """Read the host and build the environment of the selection.

    Parameters
    ----------
    directories : list of Path
        Where the board packages are.
    inventory : Path, optional
        The inventory file in place of the default.
    host : str, optional
        The label of the host.
    idcode : str, optional
        The IDCODE of a board without a package; it becomes the board
        `adhoc`, returned as the second value.

    Returns
    -------
    tuple of (Environment, str or None)
        The environment and the name of the ad hoc board, if any.
    """
    boards: dict[str, BoardSpec] = load_boards(directories)
    name = None
    if idcode:
        name = "adhoc"
        boards[name] = adhoc_board(idcode, name)
    env = Environment(
        boards, load_inventory(inventory, host), read_cables(), port_path
    )
    return env, name


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
    env, _ = build_environment(boards_directories([], root))
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
