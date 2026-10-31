"""The argument parser and the `main` entry point."""

import argparse

from riscv_tools.cli.parser_board import add_board_commands
from riscv_tools.cli.parser_build import add_build_commands
from riscv_tools.cli.parser_run import add_run_commands
from riscv_tools.cli.parser_tools import add_tool_commands

_COMMANDS_WITHOUT_CONFIG = frozenset(
    {"vhdl-sort", "check-memory-map", "check-paths", "profiles"}
)
_DESCRIPTION = """Command-line entry point of ``riscv-tools``.

Usage: ``riscv-tools --config <config.yaml> <subcommand> ...``.

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.),
except `vhdl-sort`, `check-memory-map` and `check-paths`, which read
only files and need no project config at all.
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
        "(required for every subcommand except vhdl-sort, check-memory-map "
        "and check-paths)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Consuming project's root dir (default: cwd)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_build_commands(sub)
    add_board_commands(sub)
    add_run_commands(sub)
    add_tool_commands(sub)

    args = parser.parse_args()
    if args.command not in _COMMANDS_WITHOUT_CONFIG and args.config is None:
        parser.error("--config is required for this subcommand")
    args.func(args)
