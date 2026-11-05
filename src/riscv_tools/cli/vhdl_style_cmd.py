"""The subcommand that checks the style of the VHDL files."""

import argparse
import sys

from riscv_tools import vhdl_style
from riscv_tools.cli.common import project_root


def cmd_check_vhdl_style(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-vhdl-style`.

    Fails when a VHDL file of the repository breaks the style guide
    (see vhdl_style.check_vhdl_style). Doesn't touch args.config: it
    only reads the files of the repository.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.only and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 on any
        violation and with status 2 on an unknown rule.
    """
    root = project_root(args)
    only = args.only.split(",") if args.only else None
    try:
        problems = vhdl_style.check_vhdl_style(root, only)
    except ValueError as error:
        print(f"check-vhdl-style: {error}", file=sys.stderr)
        sys.exit(2)
    if problems:
        for problem in problems:
            print(f"STYLE {problem}", file=sys.stderr)
        print(f"{len(problems)} violation(s)", file=sys.stderr)
        sys.exit(1)
    print(f"vhdl style OK: rules {', '.join(only or vhdl_style.rule_names())}")
