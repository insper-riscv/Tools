"""The subcommands of the VHDL style guide, which the VSG enforces."""

import argparse
import sys

from riscv_tools import vhdl_style
from riscv_tools.cli.common import project_root


def cmd_check_vhdl_style(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-vhdl-style`.

    A shortcut for the VSG: runs it with the configuration and the
    local rules of the project over the files `vhdl-files` lists. By
    default it applies the rules the CI gate demands; `--full` applies
    every rule of `vsg.yaml`. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.full and args.root.

    Returns
    -------
    None
        Prints the output of the VSG; exits the process with status 1
        when the VSG reports a violation.
    """
    status, output = vhdl_style.run_vsg(project_root(args), args.full)
    print(output, end="", file=sys.stderr if status else sys.stdout)
    if status:
        sys.exit(1)
    print("vhdl style OK")


def cmd_vsg_config(args: argparse.Namespace) -> None:
    """Implement `riscv-tools vsg-config`.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.board.

    Returns
    -------
    None
        Prints the path of `vsg.yaml`, or of the layer for the board.
    """
    print(vhdl_style.BOARD_CONFIG if args.board else vhdl_style.CONFIG)


def cmd_vsg_rules(_args: argparse.Namespace) -> None:
    """Implement `riscv-tools vsg-rules`.

    Parameters
    ----------
    _args : argparse.Namespace
        Parsed CLI arguments; unused.

    Returns
    -------
    None
        Prints the path of the folder with the local rules.
    """
    print(vhdl_style.LOCAL_RULES)


def cmd_vhdl_files(args: argparse.Namespace) -> None:
    """Implement `riscv-tools vhdl-files`.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.board and args.root.

    Returns
    -------
    None
        Prints the VHDL files the style guide covers, one per line,
        relative to the root.
    """
    for relative in vhdl_style.vhdl_files(project_root(args), args.board):
        print(relative)
