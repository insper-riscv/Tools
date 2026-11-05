"""The subcommand that packs, checks and sends a FLASH bank image."""

import argparse
import sys
from pathlib import Path

from riscv_tools import flash_image
from riscv_tools.cli.common import jtag_link, project_root
from riscv_tools.memory_map import banks, evaluate, load_platform
from riscv_tools.settings import load_config


def _bank_size(args: argparse.Namespace) -> int | None:
    """Find the size of the bank the image must fit in.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.platform, args.bank and
        args.root.

    Returns
    -------
    int or None
        The size of the bank in the platform, or None without a bank.

    Raises
    ------
    flash_image.ImageError
        If only one of --platform and --bank is given, or the platform
        has no such bank.
    """
    if args.bank is None and args.platform is None:
        return None
    if args.bank is None or args.platform is None:
        raise flash_image.ImageError("--platform and --bank go together")
    platform = load_platform(project_root(args) / args.platform)
    for bank in banks.bank_list(platform):
        if str(bank["name"]) == args.bank:
            return evaluate(bank["size"])
    raise flash_image.ImageError(f"the platform has no bank {args.bank}")


def _pack(args: argparse.Namespace) -> None:
    """Write the image of a program."""
    if args.output is None:
        raise flash_image.ImageError("--output is required to pack")
    payload = Path(args.input).read_bytes()
    image = flash_image.pack(payload, args.version, _bank_size(args))
    Path(args.output).write_bytes(image)
    print(
        f"flash-image: {args.output}, version {args.version}, "
        f"{len(image)} bytes"
    )


def _verify(args: argparse.Namespace) -> None:
    """Check an image against its header."""
    header = flash_image.verify(Path(args.input).read_bytes())
    print(
        f"flash-image OK: version {header.version}, {header.size} bytes, "
        f"CRC 0x{header.crc:08X}"
    )


def _send(args: argparse.Namespace) -> None:
    """Send an image to the program that receives it."""
    if args.config is None:
        raise flash_image.ImageError("--config is required to send")
    image = Path(args.input).read_bytes()
    flash_image.verify(image)
    link = jtag_link(load_config(args.config))

    def show(chunk: bytes) -> None:
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()

    count = flash_image.send_image(link, image, show)
    print(f"flash-image: sent {count} bytes", file=sys.stderr)


def cmd_flash_image(args: argparse.Namespace) -> None:
    """Implement `riscv-tools flash-image`.

    Packs a program into the image of a FLASH bank, checks an image, or
    sends it to the program that updates the FLASH. Only `send` needs
    the project config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.action, args.input,
        args.output, args.version, args.platform, args.bank, args.root
        and args.config.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 when the
        image or the arguments are invalid.
    """
    actions = {"pack": _pack, "verify": _verify, "send": _send}
    try:
        actions[args.action](args)
    except flash_image.ImageError as error:
        print(f"flash-image: {error}", file=sys.stderr)
        sys.exit(1)
