"""The subcommand that checks the layout of a repository."""

import argparse
import sys

from riscv_tools import tree_check
from riscv_tools.cli.common import project_root


def cmd_check_tree(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-tree`.

    Fails when the tree of the repository breaks a rule of its kind (see
    tree_check.check_tree). Doesn't touch args.config: it only reads the
    files of the repository.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.kind, args.only and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 on any
        problem and with status 2 on an unknown rule.
    """
    root = project_root(args)
    only = args.only.split(",") if args.only else None
    try:
        problems = tree_check.check_tree(root, args.kind, only)
        names = only or tree_check.rule_names(args.kind)
    except ValueError as error:
        print(f"check-tree: {error}", file=sys.stderr)
        sys.exit(2)
    if problems:
        for problem in problems:
            print(f"TREE {problem}", file=sys.stderr)
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        sys.exit(1)
    print(f"tree OK: {args.kind}, rules {', '.join(names)}")
