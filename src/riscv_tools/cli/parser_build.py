"""Register the subcommands that build and generate files."""

from typing import Any

from riscv_tools.cli.compile_cmd import cmd_compile
from riscv_tools.cli.golden_cmd import cmd_generate_golden, cmd_generate_header
from riscv_tools.cli.parser_util import add_command


def add_build_commands(sub: Any) -> None:
    """Register the subcommands that build and generate files.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_compile,
        "compile",
        description=(
            "Compile tests/c/{real,sim} into mif/hex/asm (+ manifest.json)"
        ),
    )
    p.add_argument("--emit", choices=["mif", "hex", "asm"], required=True)
    p.add_argument(
        "--manifest",
        default=None,
        help="Full path override for the combined manifest.json "
        "(default: <build_dir>/manifest.json)",
    )
    p.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="NAME[,NAME...]",
        help="Only build these test(s) (by folder name), instead of every "
        "test, repeatable, and/or comma-separated in one use. The "
        "manifest.json written then lists just these tests.",
    )
    p.add_argument(
        "--manifest-per-test",
        default=None,
        help='Full path template containing "{name}" (e.g. '
        '"some/dir/{name}.json"), '
        "if given, also writes each test's own manifest entry to its own file",
    )

    p = add_command(
        sub,
        cmd_generate_header,
        "generate-header",
        description=(
            "Generate rv32_test.h from config.yaml's memory.tohost_addr"
        ),
    )
    p.add_argument(
        "--out",
        default=None,
        help="Output path (default: <paths.include_dir>/rv32_test.h)",
    )

    p = add_command(
        sub,
        cmd_generate_golden,
        "generate-golden",
        description="Generate a golden JSON by running an ELF under Spike",
    )
    p.add_argument("elf")
    p.add_argument("--march", required=True, help="e.g. rv32im")
    p.add_argument(
        "--symbol",
        default=None,
        help="Data symbol to snapshot (e.g. a C global), its address and "
        "size "
        "are resolved automatically via `nm -S`, instead of --start/--end. "
        "Mutually exclusive with --start/--end.",
    )
    p.add_argument(
        "--start",
        default=None,
        help="First byte address to snapshot (hex or decimal)",
    )
    p.add_argument(
        "--end",
        default=None,
        help="One past the last byte address to snapshot (hex or decimal)",
    )
    p.add_argument(
        "--out", required=True, help="Where to write the golden .json"
    )
