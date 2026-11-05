"""The subcommand that lists the source files of a target."""

import argparse
import sys

from riscv_tools.cli.common import project_root
from riscv_tools.sources import SourcesError, ordered_sources


def cmd_sources(args: argparse.Namespace) -> None:
    """Implement `riscv-tools sources`.

    Prints, one per line, the files of the targets in analysis order
    (see sources.ordered_sources). Doesn't touch args.config: it only
    reads the `provides` manifests.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.target and args.root.

    Returns
    -------
    None
        Prints the paths; exits the process with status 2 when a target
        or manifest is invalid.
    """
    root = project_root(args)
    try:
        paths = ordered_sources(root, args.target)
    except SourcesError as error:
        print(f"sources: {error}", file=sys.stderr)
        sys.exit(2)
    for path in paths:
        print(path)
