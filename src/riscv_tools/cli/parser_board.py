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
from riscv_tools.cli.parser_util import add_command


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
        "mif", help=".mif to bake in as the ROM's init_file before compiling"
    )

    p = add_command(
        sub,
        cmd_htif,
        "htif",
        description="Read the HTIF tohost word, or write fromhost to restart",
    )
    p.add_argument("action", choices=["read", "restart"])
