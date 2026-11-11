"""Register the subcommand that works on a project."""

from typing import Any

from riscv_tools.cli.parser_util import add_command
from riscv_tools.cli.project_cmd import cmd_project
from riscv_tools.new_project import LANGUAGES
from riscv_tools.project import STOP_AFTER


def add_project_command(sub: Any) -> None:
    """Register `project` and its options.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_project,
        "project",
        description="Build, program and check a project made by "
        "new-project, without typing the Quartus or board options",
    )
    p.add_argument(
        "action",
        choices=["build", "flash", "doctor", "help"],
        help="build: compile the Quartus project; flash: program the "
        "board with a .mif; doctor: check files, Quartus and cable; "
        "help: how to run the tests and compile a program",
    )
    p.add_argument("target", nargs="?", help="flash: the .mif of a program")
    p.add_argument(
        "--dir",
        default=".",
        help="Folder inside the project (default: .)",
    )
    p.add_argument(
        "--stop-after",
        choices=STOP_AFTER,
        default="sta",
        help="build: last Quartus step to run (default: sta)",
    )
    p.add_argument(
        "--lang",
        choices=LANGUAGES,
        default="pt",
        help="help: language of the text (default: pt)",
    )
