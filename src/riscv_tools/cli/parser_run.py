"""Register the subcommands that run test suites."""

from typing import Any

from riscv_tools.cli.certify_cmd import cmd_certify, cmd_certify_board
from riscv_tools.cli.parser_util import add_command
from riscv_tools.cli.spike_cmd import cmd_spike_run
from riscv_tools.cli.suite_cmd import cmd_run, cmd_sim


def add_run_commands(sub: Any) -> None:
    """Register the subcommands that run test suites.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_run,
        "run",
        description="Run the real-hardware test suite from a manifest.json",
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Only run these test(s) (by manifest name), instead of the whole "
        "suite, repeatable, and/or comma-separated in one use. Implies you "
        "probably also want --skip-reconfigure if the board is already "
        "running a compatible bitstream.",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Omit these test(s) by manifest name, repeatable, and/or "
        "comma-separated in one use. Unknown names are errors.",
    )
    p.add_argument(
        "--skip-reconfigure",
        action="store_true",
        help="Skip the initial compile+program step and go straight to "
        "JTAG-loading each test's ROM, only safe if the board is ALREADY "
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
        "from the exact step that failed, no need to re-invoke this "
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
        "full quartus_sh --flow compile first, only safe if the VHDL "
        "source hasn't changed since that .sof was built (e.g. the "
        "board just lost its configuration to a power-cycle, not a "
        "source edit). Repeated full recompiles in one session have "
        "been observed to destabilize the JTAG chain, so prefer this "
        "over a full reconfigure when you know the .sof is still "
        "current. Unlike --skip-reconfigure, this still reprograms the "
        "board, only the compile step is skipped.",
    )

    p = add_command(
        sub,
        cmd_spike_run,
        "spike-run",
        description=(
            "Run every compiled test to completion under Spike and report "
            "PASS/FAIL"
        ),
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only", default=None, help="Comma-separated test names to run"
    )

    p = add_command(
        sub,
        cmd_sim,
        "sim",
        description=(
            "Run a simulation test suite (cocotb/GHDL) from a manifest.json"
        ),
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Only run these test(s) by manifest name, repeatable, and/or "
        "comma-separated in one use.",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Omit these test(s) by manifest name, repeatable, and/or "
        "comma-separated in one use. Unknown names are errors.",
    )

    p = add_command(
        sub,
        cmd_certify,
        "certify",
        description="Build+run the ACT4 architectural certification suite "
        "(cocotb/GHDL) for this project's own ACT4 target",
    )
    p.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated extension list forwarded to ACT4's own "
        "`make ... EXTENSIONS=` (default: config.yaml's act.extensions)",
    )

    p = add_command(
        sub,
        cmd_certify_board,
        "certify-board",
        description=(
            "Build the ACT4 ELFs of the SDRAM target and run each one on the "
            "board (loaded into the SDRAM through the debug port)"
        ),
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
