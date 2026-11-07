"""Registra `board generate` no grupo `board`."""

from typing import Any

from riscv_tools.cli.board_generate_cmd import cmd_board_generate
from riscv_tools.cli.parser_util import add_command, add_group


def add_board_group(sub: Any) -> None:
    """Registra `board generate` no grupo `board`, criado uma só vez.

    Parameters
    ----------
    sub : Any
        Os subparsers do parser principal.
    """
    group = add_group(sub, "board", "Identify, select and lock a board")
    p = add_command(
        group,
        cmd_board_generate,
        "generate",
        description="Generate the Quartus project of a platform on a board",
    )
    p.add_argument("--platform", required=True, help="platform.yaml")
    p.add_argument("--out", required=True, help="output (build) folder")
    p.add_argument("--boards-dir", default=None)
    p.add_argument("--chips-dir", default=None)
    p.add_argument(
        "--target",
        action="append",
        default=[],
        help="component whose source closure goes in the .qsf; repeatable",
    )
    p.add_argument("--seed", type=int, default=5)
    p.add_argument("--accept-inferred-pins", action="store_true")
    p.add_argument("--hand-qsf", default=None)
    p.add_argument("--hand-sdc", default=None)
    p.add_argument("--hand-pll", default=None)
    p.add_argument("--ignore-source", action="append", default=[])
