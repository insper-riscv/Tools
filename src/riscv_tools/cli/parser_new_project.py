"""Register the subcommand that creates a project."""

from typing import Any

from riscv_tools.cli.new_project_cmd import cmd_new_project
from riscv_tools.cli.parser_util import add_command
from riscv_tools.new_project import DEFAULT_SOURCE, LANGUAGES


def add_new_project_command(sub: Any) -> None:
    """Register `new-project` and its options.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_new_project,
        "new-project",
        description="Create a project: download the repository, build the "
        "platform of a known board from the choices and print a short help",
    )
    p.add_argument(
        "--new",
        dest="project_title",
        required=True,
        metavar="NAME",
        help="Name of the new project: letters, digits, spaces, hyphens "
        "and underscores; the identifier for the folder and the platform "
        "is derived from it",
    )
    p.add_argument(
        "--board",
        dest="project_board",
        required=True,
        help="Board of the catalog the platform is built on",
    )
    p.add_argument(
        "--profile",
        dest="project_profile",
        help="Profile of the core, such as rv32im_zicclsm_zicntr_zihpm "
        "(default: the template's)",
    )
    p.add_argument(
        "--peripherals",
        dest="project_peripherals",
        metavar="LIST",
        help="Peripherals to write, separated by commas: ledr, sw, key, "
        "hex, uart, clint, plic (default: none, `peripherals: {}`)",
    )
    p.add_argument("--rom", help="ROM (FLASH) size, such as 64K")
    p.add_argument("--ram", help="RAM size, such as 64K")
    p.add_argument("--icache", help="Instruction cache size in bits, or off")
    p.add_argument("--dcache", help="Data cache size in bits, or off")
    p.add_argument(
        "--dir",
        default=".",
        help="Folder the project folder is created in (default: .)",
    )
    p.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="Address of the Insper-RISC-V repository to download",
    )
    p.add_argument(
        "--repo",
        help="Use this Insper-RISC-V checkout instead of downloading one",
    )
    p.add_argument(
        "--no-generate",
        action="store_true",
        help="Write the platform but do not generate the files from it",
    )
    p.add_argument(
        "--lang",
        choices=LANGUAGES,
        default="pt",
        help="Language of the printed help (default: pt)",
    )
