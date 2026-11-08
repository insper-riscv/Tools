"""The subcommand that checks the board catalog."""

import argparse
import sys

from riscv_tools.board_check import check_catalog
from riscv_tools.board_schema import Catalog
from riscv_tools.cli.common import project_root


def cmd_check_boards(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-boards`.

    Reads every board, family, chip and pins file of the catalog found
    from the root and checks them against their schemas and against each
    other. Doesn't touch args.config: it only reads the catalog.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 on any
        problem.
    """
    catalog = Catalog.for_root(project_root(args))
    problems = check_catalog(catalog)
    if problems:
        for problem in problems:
            print(f"BOARDS {problem}", file=sys.stderr)
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        sys.exit(1)
    print(
        f"boards OK: {len(catalog.board_names())} boards, "
        f"{len(catalog.family_names())} families, "
        f"{len(catalog.chip_names())} chips"
    )
