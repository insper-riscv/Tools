"""Register the subcommands that only read files or run small tools."""

from typing import Any

from riscv_tools.cli.flash_image_cmd import cmd_flash_image
from riscv_tools.cli.parser_util import add_command
from riscv_tools.cli.platform_cmd import cmd_platform
from riscv_tools.cli.sources_cmd import cmd_sources
from riscv_tools.cli.tools_cmd import (
    cmd_check_memory_map,
    cmd_check_paths,
    cmd_freq_sweep,
    cmd_generate_memory_map,
    cmd_profiles,
    cmd_timing_paths,
    cmd_vhdl_sort,
)
from riscv_tools.cli.tree_cmd import cmd_check_tree
from riscv_tools.cli.vhdl_style_cmd import cmd_check_vhdl_style
from riscv_tools.tree_check import KINDS

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
    p.add_argument(
        "--accept-inferred-pins",
        action="store_true",
        help="Allow a board pin that is only inferred (rule V16)",
    )

    p = add_command(
        sub,
        cmd_generate_memory_map,
        "generate-memory-map",
        description=(
            "Write the linker flags, the boot memory linker script and the "
            "VHDL package of the map from the platform YAML"
        ),
    )
    p.add_argument(
        "--platform",
        required=True,
        help="Platform YAML (relative to --root): the map and `generate`",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Only compare the generated files with what is on disk",
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
        cmd_check_tree,
        "check-tree",
        description=(
            "Fail when the tree of a repository breaks the layout every "
            "repository shares"
        ),
    )
    p.add_argument(
        "--kind",
        required=True,
        choices=KINDS,
        help="Kind of repository, which decides the rules that apply",
    )
    p.add_argument(
        "--only",
        help="Comma-separated rules to run (default: every rule of the "
        "kind); a repository that has not finished its reorganization "
        "names the rules it already meets",
    )

    p = add_command(
        sub,
        cmd_sources,
        "sources",
        description=(
            "Print the source files of a target in analysis order, read "
            "from the `provides` manifests of the repository and of the "
            "ones mounted below it"
        ),
    )
    p.add_argument(
        "target",
        nargs="+",
        help="Component to build, as <repository>/<component>; a bare "
        "name is a component of the repository at --root",
    )

    p = add_command(
        sub,
        cmd_check_vhdl_style,
        "check-vhdl-style",
        description=(
            "Fail when a VHDL file breaks the style guide of the project "
            "(vendor code and Quartus IPs are left out)"
        ),
    )
    p.add_argument(
        "--only",
        help="Comma-separated rules to run (default: every rule)",
    )

    p = add_command(
        sub,
        cmd_platform,
        "platform",
        description=(
            "Write the config of a platform with its paths rebased onto the "
            "project that consumes it"
        ),
    )
    p.add_argument("action", choices=["sync"], help="What to do with it")
    p.add_argument(
        "--source",
        required=True,
        help="Platform config.yaml (relative to --root), its extends chain "
        "is resolved",
    )
    p.add_argument(
        "--prefix",
        required=True,
        help="Folder of the platform repository in the consumer, put in "
        "front of the platform's paths",
    )
    p.add_argument(
        "--output",
        required=True,
        help="File to write (relative to --root)",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Write nothing and fail when the file is missing or differs",
    )

    p = add_command(
        sub,
        cmd_flash_image,
        "flash-image",
        description="Pack a program into the image of a FLASH bank, check "
        "an image or send it over the JTAG UART",
    )
    p.add_argument(
        "action",
        choices=["pack", "verify", "send"],
        help="pack: header and payload into an image; verify: check an "
        "image; send: give an image to the program that updates the FLASH "
        "(needs --config)",
    )
    p.add_argument(
        "input",
        help="pack: the program (.bin); verify and send: the image",
    )
    p.add_argument("--output", help="pack: the image to write")
    p.add_argument(
        "--version",
        type=int,
        default=0,
        help="pack: version of the image (default 0)",
    )
    p.add_argument(
        "--platform",
        help="pack: platform YAML (relative to --root) with the bank",
    )
    p.add_argument(
        "--bank",
        help="pack: name of the bank of the platform the image must fit",
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
