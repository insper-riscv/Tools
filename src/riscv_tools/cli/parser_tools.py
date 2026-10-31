"""Register the subcommands that only read files or run small tools."""

from typing import Any

from riscv_tools.cli.parser_util import add_command
from riscv_tools.cli.tools_cmd import (
    cmd_check_memory_map,
    cmd_check_paths,
    cmd_freq_sweep,
    cmd_profiles,
    cmd_timing_paths,
    cmd_vhdl_sort,
)

_DEFAULT_NPATHS = 30


def add_tool_commands(sub: Any) -> None:
    """Register the subcommands that only read files or run small tools.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_profiles,
        "profiles",
        description="List every valid core profile of a profile specification",
    )
    p.add_argument(
        "--spec",
        required=True,
        help="YAML with the extensions and their rules",
    )
    p.add_argument(
        "--format",
        choices=["names", "json", "generics"],
        default="names",
        help="names: one per line; generics: name and GHDL -g flags; json: "
        "all",
    )

    p = add_command(
        sub,
        cmd_vhdl_sort,
        "vhdl-sort",
        description=(
            "Print VHDL files in GHDL analyze order (dependencies first)"
        ),
    )
    p.add_argument("files", nargs="+", help="VHDL source files to order")

    p = add_command(
        sub,
        cmd_check_memory_map,
        "check-memory-map",
        description=(
            "Check every hand-written copy of the memory map against the "
            "platform YAML"
        ),
    )
    p.add_argument(
        "--platform",
        required=True,
        help="Platform YAML (relative to --root): the map and the checks",
    )

    p = add_command(
        sub,
        cmd_check_paths,
        "check-paths",
        description=(
            "Fail when a file path listed in the project's configuration does"
            " not exist"
        ),
    )
    p.add_argument(
        "--manifest",
        required=True,
        help="Manifest YAML (relative to --root) listing the references to "
        "check",
    )

    p = add_command(
        sub,
        cmd_timing_paths,
        "timing-paths",
        description="List the worst setup paths of every clock domain of the "
        "compiled "
        "Quartus project, grouped by register",
    )
    p.add_argument(
        "--npaths",
        type=int,
        default=_DEFAULT_NPATHS,
        help=(
            "Setup paths to ask for in each clock domain "
            f"(default: {_DEFAULT_NPATHS})"
        ),
    )
    p.add_argument(
        "--model",
        choices=["slow", "fast"],
        default="slow",
        help="Timing model (default: slow, 1100 mV and 85 C)",
    )
    p.add_argument("--out", help="Also write the table to this file")

    p = add_command(
        sub,
        cmd_freq_sweep,
        "freq-sweep",
        description="Sweep/binary-search clock frequency to find Fmax "
        "(edits the PLL + full recompile+reprogram per candidate)",
    )
    p.add_argument(
        "mif",
        help=".mif to bake in as the ROM's init_file at every candidate "
        "frequency",
    )
    p.add_argument(
        "--golden",
        required=True,
        help="Golden JSON the post-run RAM dump is compared against",
    )
    p.add_argument(
        "--binary",
        action="store_true",
        help="Binary search instead of linear sweep",
    )
    p.add_argument(
        "--start", type=float, default=1.0, help="(linear) start freq, MHz"
    )
    p.add_argument(
        "--stop", type=float, default=30.0, help="(linear) stop freq, MHz"
    )
    p.add_argument(
        "--step", type=float, default=2.0, help="(linear) step, MHz"
    )
    p.add_argument(
        "--low", type=float, default=1.0, help="(binary) low bound, MHz"
    )
    p.add_argument(
        "--high", type=float, default=50.0, help="(binary) high bound, MHz"
    )
    p.add_argument(
        "--out",
        default=None,
        help="Results JSON path "
        "(default: <build_dir>/freq_sweep/freq_sweep_results.json)",
    )
