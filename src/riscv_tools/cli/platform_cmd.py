"""The subcommand that writes a platform config for its consumer."""

import argparse
import sys
from pathlib import Path

from riscv_tools import platform_sync
from riscv_tools.cli.common import project_root


def cmd_platform(args: argparse.Namespace) -> None:
    """Implement `riscv-tools platform sync`.

    Reads the platform config, puts the folder of the platform
    submodule in front of its paths and writes the result, or with
    --check fails when the file on disk is not what would be written.
    Doesn't touch args.config: it only reads and writes the files named
    by its own arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.action, args.source,
        args.prefix, args.output, args.check and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 when --check
        finds the file missing or different.
    """
    root = project_root(args)
    source = root / args.source
    output = root / args.output
    config = platform_sync.rebase(platform_sync.flatten(source), args.prefix)
    text = platform_sync.render(config, args.source, args.prefix)
    if args.check:
        problems = platform_sync.check_output(output, text)
        for problem in problems:
            print(f"PLATFORM {problem}", file=sys.stderr)
        if problems:
            sys.exit(1)
        print(f"platform OK: {Path(args.output)}")
        return
    platform_sync.write_output(output, text)
    print(f"platform synced: {Path(args.output)}")
