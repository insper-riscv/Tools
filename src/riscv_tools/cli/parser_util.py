"""Helper shared by the modules that register the subcommands."""

import argparse
from collections.abc import Callable
from typing import Any


def add_command(
    sub: Any,
    func: Callable[[argparse.Namespace], None],
    name: str,
    description: str,
) -> argparse.ArgumentParser:
    """Register a subcommand and the handler that runs it.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    func : Callable
        The cmd_* function that implements the subcommand.
    name : str
        The subcommand name on the command line.
    description : str
        The one-line description shown in the usage.

    Returns
    -------
    argparse.ArgumentParser
        The parser of the subcommand, ready for add_argument.
    """
    parser = sub.add_parser(name, help=description)
    parser.set_defaults(func=func)
    return parser
