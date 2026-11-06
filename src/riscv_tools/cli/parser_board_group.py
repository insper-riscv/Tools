"""Registra o grupo `board` e o subcomando `board generate`."""

from typing import Any

from riscv_tools.cli.board_generate_cmd import cmd_board_generate


def add_board_group(sub: Any) -> Any:
    """Registra `board` e `board generate`.

    Os demais subcomandos de `board` (`scan`, `select`, `lock`,
    `doctor`) entram no valor devolvido.

    Parameters
    ----------
    sub : Any
        Os subparsers do parser principal.

    Returns
    -------
    Any
        Os subparsers do grupo `board`.
    """
    group = sub.add_parser("board", help="Boards: generate their project")
    actions = group.add_subparsers(dest="board_command", required=True)
    p = actions.add_parser(
        "generate",
        help="Generate the Quartus project of a platform on a board",
    )
    p.set_defaults(func=cmd_board_generate)
    p.add_argument("--platform", required=True, help="platform.yaml")
    p.add_argument("--board", default=None, help="board name")
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
    return actions
