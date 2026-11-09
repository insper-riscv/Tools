"""Register the `ipxact` command group."""

from typing import Any

from riscv_tools.cli.ipxact_cmd import (
    cmd_ipxact_check,
    cmd_ipxact_extract,
    cmd_ipxact_generate,
)
from riscv_tools.cli.parser_util import add_command, add_group


def add_ipxact_commands(sub: Any) -> None:
    """Register `ipxact extract`, `ipxact generate` and `ipxact check`.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    group = add_group(
        sub, "ipxact", "Extract, generate and check IP-XACT descriptions"
    )
    add_command(
        group,
        cmd_ipxact_extract,
        "extract",
        "Print the generics and ports of every entity, read from the VHDL",
    )
    parser = add_command(
        group,
        cmd_ipxact_generate,
        "generate",
        "Write the ipxact:component of every entity",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; fail when a stored document differs from the "
        "one the VHDL gives",
    )
    add_command(
        group,
        cmd_ipxact_check,
        "check",
        "Fail when the stored documents are stale or break IEEE 1685-2022",
    )
