"""Register the board identification subcommands."""

import argparse
from typing import Any

from riscv_tools.cli.board_id_cmd import (
    cmd_board_doctor,
    cmd_board_lock,
    cmd_board_scan,
    cmd_board_select,
)
from riscv_tools.cli.parser_util import add_command, add_group


def _host_options(p: argparse.ArgumentParser) -> None:
    """Add the options that say where the boards and inventory are."""
    p.add_argument(
        "--boards-dir",
        action="append",
        default=[],
        help="directory of the board packages (<dir>/<board>/board.yaml); "
        "repeatable; RISCV_TOOLS_BOARDS and <root>/Insper-RISC-V/boards "
        "also count",
    )
    p.add_argument(
        "--inventory",
        default=None,
        help="inventory file in place of ~/.config/riscv-tools/boards.yaml",
    )
    p.add_argument(
        "--host",
        default=None,
        help="label of the host in the lock file names (default: the short "
        "hostname, or RISCV_TOOLS_HOST)",
    )


def _select_options(p: argparse.ArgumentParser) -> None:
    """Add the options of the board choice."""
    p.add_argument("--board", default=None, help="board identifier")
    p.add_argument("--board-id", default=None, help="entry of the inventory")
    p.add_argument(
        "--cable",
        default=None,
        help="force the cable name (IDCODE still checked)",
    )
    p.add_argument(
        "--platform",
        default=None,
        help="platform.yaml whose `board:` and `boards:` apply",
    )
    p.add_argument(
        "--free",
        action="store_true",
        help="among equal boards take the first one whose lock is free",
    )


def add_board_id_commands(sub: Any) -> None:
    """Register the board identification subcommands.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    group = add_group(sub, "board", "Identify, select and lock a board")
    p = add_command(
        group,
        cmd_board_scan,
        "scan",
        description="List the cables of the host and the boards they are",
    )
    _host_options(p)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--save", action="store_true", help="record the certain cables"
    )
    p.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="PORT=BOARD",
        help="board of an ambiguous port, for --save",
    )

    p = add_command(
        group,
        cmd_board_select,
        "select",
        description="Choose the board and the cable of a platform",
    )
    _host_options(p)
    _select_options(p)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--all", action="store_true", help="list every present board"
    )

    p = add_command(
        group,
        cmd_board_lock,
        "lock",
        description="Lock the selected board while a command runs",
    )
    _host_options(p)
    _select_options(p)
    p.add_argument(
        "--wait",
        type=float,
        nargs="?",
        const=14400.0,
        default=0.0,
        help="seconds to wait for a busy board (default 0; 14400 alone)",
    )
    p.add_argument(
        "--hold",
        action="store_true",
        help="print the selection and hold the lock until stdin closes",
    )
    p.add_argument("lock_command", metavar="command", nargs=argparse.REMAINDER)

    p = add_command(
        group,
        cmd_board_doctor,
        "doctor",
        description="Check cables, chains and processes; changes nothing",
    )
    _host_options(p)
    p.add_argument("--json", action="store_true")
