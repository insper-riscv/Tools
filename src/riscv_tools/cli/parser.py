"""The argument parser and the `main` entry point."""

import argparse
from typing import Any

from riscv_tools.cli.board_cmd import (
    cmd_console,
    cmd_display,
    cmd_dump_ram,
    cmd_mailbox,
    cmd_program,
    cmd_write_rom,
    cmd_zero_ram,
)
from riscv_tools.cli.certify_cmd import cmd_certify, cmd_certify_board
from riscv_tools.cli.compile_cmd import cmd_compile
from riscv_tools.cli.golden_cmd import cmd_generate_golden, cmd_generate_header
from riscv_tools.cli.spike_cmd import cmd_spike_run
from riscv_tools.cli.suite_cmd import cmd_run, cmd_sim
from riscv_tools.cli.tools_cmd import (
    cmd_check_memory_map,
    cmd_check_paths,
    cmd_freq_sweep,
    cmd_profiles,
    cmd_timing_paths,
    cmd_vhdl_sort,
)

# Statement count grows with each subcommand's own add_argument calls
# (repetitive parser wiring, not real branching complexity) — splitting
# it up would just move the same lines behind indirection.
_DESCRIPTION = """Command-line entry point of ``riscv-tools``.

Usage: ``riscv-tools --config <config.yaml> <subcommand> ...``.

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.),
except `vhdl-sort`, `check-memory-map` and `check-paths`, which read
only files and need no project config at all.
"""


def _add_subcommands_1(sub: Any) -> None:
    """Register a group of subcommands.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = sub.add_parser(
        "compile",
        help="Compile tests/c/{real,sim} into mif/hex/asm (+ manifest.json)",
    )
    p.add_argument("--emit", choices=["mif", "hex", "asm"], required=True)
    p.add_argument(
        "--manifest",
        default=None,
        help="Full path override for the combined manifest.json "
        "(default: <build_dir>/manifest.json)",
    )
    p.add_argument(
        "--manifest-per-test",
        default=None,
        help='Full path template containing "{name}" (e.g. '
        '"some/dir/{name}.json") — '
        "if given, also writes each test's own manifest entry to its own file",
    )
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser(
        "write-rom", help="JTAG-write a .mif into the ROM instance"
    )
    p.add_argument("mif")
    p.set_defaults(func=cmd_write_rom)

    p = sub.add_parser("zero-ram", help="JTAG-zero the whole RAM instance")
    p.set_defaults(func=cmd_zero_ram)

    p = sub.add_parser(
        "dump-ram",
        help="JTAG-dump the RAM to a .mif (a RAM in the SDRAM: only --words "
        "words)",
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
    p.set_defaults(func=cmd_dump_ram)

    p = sub.add_parser(
        "console",
        help="Show the program's output through the JTAG UART while it runs",
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
    p.set_defaults(func=cmd_console)

    p = sub.add_parser(
        "display",
        help="Read or write the seven-segment display register of the "
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
    p.set_defaults(func=cmd_display)

    p = sub.add_parser(
        "program",
        help="Compile the Quartus project and program the board (full "
        "reconfigure)",
    )
    p.add_argument(
        "mif", help=".mif to bake in as the ROM's init_file before compiling"
    )
    p.set_defaults(func=cmd_program)

    p = sub.add_parser(
        "mailbox",
        help="Read the PASS/FAIL mailbox, or pulse the restart go-flag",
    )
    p.add_argument("action", choices=["read", "pulse"])
    p.set_defaults(func=cmd_mailbox)

    p = sub.add_parser(
        "profiles",
        help="List every valid core profile of a profile specification",
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
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser(
        "generate-header",
        help="Generate rv32_test.h from config.yaml's memory.mailbox_addr",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Output path (default: <paths.include_dir>/rv32_test.h)",
    )
    p.set_defaults(func=cmd_generate_header)


def _add_subcommands_2(sub: Any) -> None:
    """Register a group of subcommands.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = sub.add_parser(
        "generate-golden",
        help="Generate a golden JSON by running an ELF under Spike",
    )
    p.add_argument("elf")
    p.add_argument("--march", required=True, help="e.g. rv32im")
    p.add_argument(
        "--symbol",
        default=None,
        help="Data symbol to snapshot (e.g. a C global) — its address and "
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
    p.set_defaults(func=cmd_generate_golden)

    p = sub.add_parser(
        "run", help="Run the real-hardware test suite from a manifest.json"
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Only run these test(s) (by manifest name), instead of the whole "
        "suite — repeatable, and/or comma-separated in one use. Implies you "
        "probably also want --skip-reconfigure if the board is already "
        "running a compatible bitstream.",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Omit these test(s) by manifest name — repeatable, and/or "
        "comma-separated in one use. Unknown names are errors.",
    )
    p.add_argument(
        "--skip-reconfigure",
        action="store_true",
        help="Skip the initial compile+program step and go straight to "
        "JTAG-loading each test's ROM — only safe if the board is ALREADY "
        "programmed with a compatible bitstream (e.g. re-running a few "
        "tests that failed earlier in the same session). Getting this wrong "
        "looks like every test timing out, not a clean error.",
    )
    p.add_argument(
        "--wait-for-hardware",
        action="store_true",
        help="On a hardware failure that would normally stop the suite "
        "(see NeedsHumanInterventionError), stay running instead of "
        "exiting: print the same message, poll `jtagconfig` every few "
        "seconds until the chain reports healthy again (e.g. after you "
        "physically power-cycle the board), then automatically resume "
        "from the exact step that failed — no need to re-invoke this "
        "command by hand. Meant for an interactive local session someone "
        "is actively watching; CI should keep the default "
        "stop-and-exit-2 behavior instead, since nothing there could "
        "power-cycle the board on its own anyway.",
    )
    p.add_argument(
        "--skip-recompile",
        action="store_true",
        help="On the initial reconfigure step, reprogram from the "
        "already-built .sof (quartus_pgm only, ~10s) instead of doing a "
        "full quartus_sh --flow compile first — only safe if the VHDL "
        "source hasn't changed since that .sof was built (e.g. the "
        "board just lost its configuration to a power-cycle, not a "
        "source edit). Repeated full recompiles in one session have "
        "been observed to destabilize the JTAG chain, so prefer this "
        "over a full reconfigure when you know the .sof is still "
        "current. Unlike --skip-reconfigure, this still reprograms the "
        "board — only the compile step is skipped.",
    )
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "spike-run",
        help="Run every compiled test to completion under Spike and report "
        "PASS/FAIL",
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only", default=None, help="Comma-separated test names to run"
    )
    p.set_defaults(func=cmd_spike_run)

    p = sub.add_parser(
        "sim",
        help="Run a simulation test suite (cocotb/GHDL) from a manifest.json",
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Only run these test(s) by manifest name — repeatable, and/or "
        "comma-separated in one use.",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Omit these test(s) by manifest name — repeatable, and/or "
        "comma-separated in one use. Unknown names are errors.",
    )
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser(
        "certify",
        help="Build+run the ACT4 architectural certification suite "
        "(cocotb/GHDL) for this project's own ACT4 target",
    )
    p.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated extension list forwarded to ACT4's own "
        "`make ... EXTENSIONS=` (default: config.yaml's act.extensions)",
    )
    p.set_defaults(func=cmd_certify)

    p = sub.add_parser(
        "certify-board",
        help="Build the ACT4 ELFs of the SDRAM target and run each one on the "
        "board "
        "(loaded into the SDRAM through the debug port)",
    )
    p.add_argument(
        "--extensions", default=None, help="Overrides act.extensions"
    )
    p.add_argument(
        "--only", default=None, help="Comma-separated ELF names to run"
    )
    p.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the ELFs that an earlier `certify` built, without ACT4's "
        "`make`",
    )
    p.set_defaults(func=cmd_certify_board)

    p = sub.add_parser(
        "vhdl-sort",
        help="Print VHDL files in GHDL analyze order (dependencies first)",
    )
    p.add_argument("files", nargs="+", help="VHDL source files to order")
    p.set_defaults(func=cmd_vhdl_sort)

    p = sub.add_parser(
        "check-memory-map",
        help="Check every hand-written copy of the memory map against the "
        "platform YAML",
    )
    p.add_argument(
        "--platform",
        required=True,
        help="Platform YAML (relative to --root): the map and the checks",
    )
    p.set_defaults(func=cmd_check_memory_map)


def _add_subcommands_3(sub: Any) -> None:
    """Register a group of subcommands.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = sub.add_parser(
        "check-paths",
        help="Fail when a file path listed in the project's configuration "
        "does not exist",
    )
    p.add_argument(
        "--manifest",
        required=True,
        help="Manifest YAML (relative to --root) listing the references to "
        "check",
    )
    p.set_defaults(func=cmd_check_paths)

    p = sub.add_parser(
        "timing-paths",
        help="List the worst setup paths of every clock domain of the "
        "compiled "
        "Quartus project, grouped by register",
    )
    p.add_argument(
        "--npaths",
        type=int,
        default=30,
        help="Setup paths to ask for in each clock domain (default: 30)",
    )
    p.add_argument(
        "--model",
        choices=["slow", "fast"],
        default="slow",
        help="Timing model (default: slow, 1100 mV and 85 C)",
    )
    p.add_argument("--out", help="Also write the table to this file")
    p.set_defaults(func=cmd_timing_paths)

    p = sub.add_parser(
        "freq-sweep",
        help="Sweep/binary-search clock frequency to find Fmax "
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
    p.set_defaults(func=cmd_freq_sweep)


def main() -> None:
    """CLI entry point (console script `riscv-tools`).

    Builds the argument parser, registers every subcommand, and
    dispatches to its cmd_* handler. Reads sys.argv via argparse; no
    parameters.

    Returns
    -------
    None
        Exits the process with a non-zero status on argument errors,
        or whatever the dispatched cmd_* function causes (see each
        cmd_*'s own Returns/Raises).
    """
    parser = argparse.ArgumentParser(
        prog="riscv-tools",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the consuming project's config.yaml "
        "(required for every subcommand except vhdl-sort, check-memory-map "
        "and check-paths)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Consuming project's root dir (default: cwd)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _add_subcommands_1(sub)
    _add_subcommands_2(sub)
    _add_subcommands_3(sub)

    args = parser.parse_args()
    if (
        args.command
        not in {"vhdl-sort", "check-memory-map", "check-paths", "profiles"}
        and args.config is None
    ):
        parser.error("--config is required for this subcommand")
    args.func(args)
