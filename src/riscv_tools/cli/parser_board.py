"""Register the subcommands that talk to the board."""

from typing import Any

from riscv_tools.cli.board_cmd import (
    cmd_console,
    cmd_display,
    cmd_dump_ram,
    cmd_htif,
    cmd_program,
    cmd_write_rom,
    cmd_zero_ram,
)
from riscv_tools.cli.flash_load_cmd import cmd_load_flash
from riscv_tools.cli.parser_util import add_command
from riscv_tools.cli.ram_load_cmd import DEFAULT_MAGIC, cmd_load_ram


def _integer(text: str) -> int:
    """Read an integer argument in decimal, hex (0x) or binary (0b).

    Parameters
    ----------
    text : str
        The text of the argument.

    Returns
    -------
    int
        The value.
    """
    return int(text, 0)


def add_board_commands(sub: Any) -> None:
    """Register the subcommands that talk to the board.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_write_rom,
        "write-rom",
        description="JTAG-write a .mif into the ROM instance",
    )
    p.add_argument("mif")

    p = add_command(
        sub,
        cmd_zero_ram,
        "zero-ram",
        description="JTAG-zero the whole RAM instance",
    )

    p = add_command(
        sub,
        cmd_dump_ram,
        "dump-ram",
        description=(
            "JTAG-dump the RAM to a .mif (a RAM in the SDRAM: only --words "
            "words)"
        ),
    )
    p.add_argument("out")
    p.add_argument(
        "--start-word",
        type=int,
        default=0,
        help="first word offset to dump from the base of the RAM (with "
        "--words)",
    )
    p.add_argument(
        "--words",
        type=int,
        default=None,
        help="how many words to dump; required when the RAM is in the SDRAM",
    )
    p.add_argument(
        "--region",
        choices=["FLASH", "RAM", "flash", "ram"],
        default=None,
        help="dump a region that sits in the SDRAM instead of the RAM "
        "instance; out ending in .bin is written as bytes, else as a .mif",
    )
    p.add_argument(
        "--range",
        default=None,
        metavar="ADDRESS:LENGTH",
        help="with --region: byte address and length in bytes of the part "
        "to read (for example 0x41FFF000:0x1000)",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="with --region: read the whole region (uses the burst of the "
        "debug port)",
    )
    p.add_argument(
        "--platform",
        default=None,
        help="with --region: platform YAML (relative to --root) that gives "
        "the windows of the SDRAM, in place of memory.sdram_windows",
    )

    p = add_command(
        sub,
        cmd_load_ram,
        "load-ram",
        description=(
            "JTAG-load a binary (and a second file) into the SDRAM, read it "
            "back and write the launch magic last"
        ),
    )
    p.add_argument("binary", help="file loaded at --address")
    p.add_argument(
        "--address",
        type=_integer,
        default=None,
        help="byte address of the binary; the base of the RAM by default",
    )
    p.add_argument(
        "--wad", default=None, help="second file, loaded at --wad-address"
    )
    p.add_argument(
        "--wad-address",
        type=_integer,
        default=None,
        help="byte address of the second file (required with --wad)",
    )
    p.add_argument(
        "--launch-address",
        type=_integer,
        default=None,
        help="byte address of the launch word; memory.launch_addr by default",
    )
    p.add_argument(
        "--magic",
        type=_integer,
        default=DEFAULT_MAGIC,
        help="value written to the launch word last (default 0x4D4F4F44)",
    )
    p.add_argument(
        "--no-launch",
        action="store_true",
        help="load without writing the launch word",
    )
    p.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the read-back of each file",
    )

    p = add_command(
        sub,
        cmd_load_flash,
        "load-flash",
        description=(
            "Hold the core, write a program into the FLASH window of the "
            "SDRAM through the debug port, check it by the CRC-32 of the "
            "board and release the core"
        ),
    )
    p.add_argument("--image", default=None, help="packed bank image (.bin)")
    p.add_argument("--elf", default=None, help="ELF of the program")
    p.add_argument(
        "--bank",
        default=None,
        help="bank of the platform that receives it (an ELF is packed with "
        "the header of the bank)",
    )
    p.add_argument(
        "--address",
        type=_integer,
        default=None,
        help="byte address of --image without a bank",
    )
    p.add_argument(
        "--version",
        type=int,
        default=1,
        help="version of the image packed from an ELF (default 1)",
    )
    p.add_argument(
        "--platform",
        default=None,
        help="platform YAML (relative to --root) that gives the windows and "
        "the banks, in place of the project config",
    )

    p = add_command(
        sub,
        cmd_console,
        "console",
        description=(
            "Show the program's output through the JTAG UART while it runs"
        ),
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=0,
        help="how long to listen; 0 (the default) listens until Ctrl-C",
    )
    p.add_argument(
        "--send",
        default="",
        help="text to give to the program as it starts listening",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="give the program each line you type, until the input ends "
        "(Ctrl-D)",
    )

    p = add_command(
        sub,
        cmd_display,
        "display",
        description="Read or write the seven-segment display register of the "
        "platform",
    )
    p.add_argument(
        "value",
        nargs="?",
        default=None,
        help="six hex digits to show (HEX5 first); omit to only read the "
        "register",
    )
    p.add_argument(
        "--check",
        type=int,
        default=0,
        metavar="N",
        help="write N pseudo-random values and read each back; exit 1 on a "
        "difference",
    )

    p = add_command(
        sub,
        cmd_program,
        "program",
        description="Compile the Quartus project and program the board (full "
        "reconfigure)",
    )
    p.add_argument(
        "mif",
        nargs="?",
        default=None,
        help=".mif to bake in as the ROM's init_file before compiling "
        "(required unless --compile-only or --stop-after)",
    )
    p.add_argument(
        "--project-dir",
        default=None,
        help="Quartus project folder, in place of quartus.project_dir "
        "(for a project written by `board generate`)",
    )
    p.add_argument(
        "--project-name",
        default=None,
        help="Quartus revision, in place of quartus.project_name",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="placement seed (compiles through the single compile script)",
    )
    p.add_argument(
        "--generic",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="top-level generic changed for this compile only; repeatable",
    )
    p.add_argument(
        "--stop-after",
        choices=["map", "fit", "sta"],
        default=None,
        help="stop the compile after this stage (the board is not programmed)",
    )
    p.add_argument(
        "--compile-only",
        action="store_true",
        help="compile without programming the board",
    )

    p = add_command(
        sub,
        cmd_htif,
        "htif",
        description="Read the HTIF tohost word, or write fromhost to restart",
    )
    p.add_argument("action", choices=["read", "restart"])
