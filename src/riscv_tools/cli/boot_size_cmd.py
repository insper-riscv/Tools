"""The subcommand that measures the boot memory of a platform."""

import argparse
import sys
import tempfile
from pathlib import Path

from riscv_tools import boot_size
from riscv_tools.cli.common import project_root


def cmd_check_boot_size(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-boot-size`.

    Assembles the `boot_memory.S` of a platform with the toolchain and
    fails when it does not fit the BOOT_MEMORY (see
    boot_size.measure_boot_size). Doesn't touch args.config: the
    platform file names everything it reads.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.platform, args.gcc,
        args.objdump, args.build_dir and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 when the
        boot memory is too big and with status 2 when there is nothing
        to measure or the toolchain fails.
    """
    root = project_root(args)
    platform = Path(args.platform)
    if not platform.is_absolute():
        platform = root / platform
    with tempfile.TemporaryDirectory() as scratch:
        build_dir = Path(args.build_dir or scratch)
        try:
            size = boot_size.measure_boot_size(
                platform, root, build_dir, args.gcc, args.objdump
            )
        except ValueError as error:
            print(f"check-boot-size: {error}", file=sys.stderr)
            sys.exit(2)
    message = boot_size.boot_size_message(size)
    if not size.fits:
        print(message, file=sys.stderr)
        sys.exit(1)
    print(message)
