"""Register the subcommands of the board catalog."""

from typing import Any

from riscv_tools.cli.catalog_cmd import cmd_check_boards
from riscv_tools.cli.parser_util import add_command


def add_catalog_commands(sub: Any) -> None:
    """Register the subcommands that read the board catalog.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    add_command(
        sub,
        cmd_check_boards,
        "check-boards",
        description=(
            "Check the boards, families and chips of the catalog against "
            "their schemas and against each other"
        ),
    )
