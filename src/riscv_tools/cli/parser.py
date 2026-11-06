"""The argument parser and the `main` entry point."""

import argparse

from riscv_tools.cli.parser_board import add_board_commands
from riscv_tools.cli.parser_board_group import add_board_group
from riscv_tools.cli.parser_build import add_build_commands
from riscv_tools.cli.parser_run import add_run_commands
from riscv_tools.cli.parser_tools import add_tool_commands
from riscv_tools.memory_map.memory import set_override as set_memory_override
from riscv_tools.memory_map.profile import set_override as set_profile_override

_COMMANDS_WITHOUT_CONFIG = frozenset(
    {
        "board",
        "vhdl-sort",
        "check-memory-map",
        "check-paths",
        "check-tree",
        "check-vhdl-style",
        "flash-image",
        "generate-memory-map",
        "platform",
        "profiles",
        "sources",
    }
)
_DESCRIPTION = """Command-line entry point of ``riscv-tools``.

Usage: ``riscv-tools --config <config.yaml> <subcommand> ...``.

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.),
except `vhdl-sort`, `check-memory-map`, `generate-memory-map`,
`check-paths`, `check-tree`, `sources`, `platform` and `flash-image`
(except `send`), which read only files and need no project config at
all.
"""


def main() -> None:
    """CLI entry point (console script `riscv-tools`).

    Builds the argument parser, registers every subcommand, and
    dispatches to its cmd_* handler. Reads sys.argv via argparse; no
    parameters.

    Returns
    -------
    None
        Exits the process with a non-zero status on argument errors,
        or whatever the dispatched cmd_* function causes (see each
        cmd_*'s own Returns/Raises).
    """
    parser = argparse.ArgumentParser(
        prog="riscv-tools",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the consuming project's config.yaml "
        "(required for every subcommand except vhdl-sort, check-memory-map, "
        "check-paths, check-tree, sources, generate-memory-map and platform)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Consuming project's root dir (default: cwd)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Profile of the platform (rv32im, rv32em_zicsr, ...) in place "
        "of the `profile:` of its platform.yaml; it sets the base ISA, "
        "the generics of the simulation and the generated VHDL package",
    )
    parser.add_argument(
        "--memory",
        default=None,
        help="Memories and caches of the platform, in place of fields of "
        "its `memory:` section: a comma list such as "
        "rom=ext,ram=int,icache=on,dcache=4096 (rom and ram take int or "
        "ext; icache and dcache take on, off or a size in bits)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_build_commands(sub)
    add_board_commands(sub)
    add_board_group(sub)
    add_run_commands(sub)
    add_tool_commands(sub)

    args = parser.parse_args()
    set_profile_override(args.profile)
    try:
        set_memory_override(args.memory)
    except ValueError as error:
        parser.error(str(error))
    if args.command not in _COMMANDS_WITHOUT_CONFIG and args.config is None:
        parser.error("--config is required for this subcommand")
    args.func(args)
