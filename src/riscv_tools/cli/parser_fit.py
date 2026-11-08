"""Register the subcommands of the fit check."""

from typing import Any

from riscv_tools.cli.calibrate_cmd import cmd_calibrate, cmd_check_fit
from riscv_tools.cli.parser_util import add_command


def add_fit_commands(sub: Any) -> None:
    """Register `calibrate` and `check-fit`.

    Parameters
    ----------
    sub : Any
        The subparsers of the main parser.
    """
    p = add_command(
        sub,
        cmd_calibrate,
        "calibrate",
        description="Measure the profiles of a family with the project's "
        "synthesis (run) or fit the estimator from the records (fit)",
    )
    p.add_argument("action", choices=["run", "fit", "verify"])
    p.add_argument(
        "--profiles",
        required=True,
        help="Profile list of the family (relative to --root)",
    )
    p.add_argument(
        "--raw",
        required=True,
        help="Directory of the raw records (relative to --root)",
    )
    p.add_argument(
        "--table",
        help="fit: calibration file to write; verify: table to check",
    )
    p.add_argument(
        "--work-dir",
        help="run: directory of the throwaway project copies "
        "(default: calibration in the temporary directory)",
    )
    p.add_argument(
        "--lock",
        help="run: Quartus lock (default quartus-<host>.lock in the "
        "temporary directory)",
    )
    p.add_argument(
        "--riscv-tools",
        default="riscv-tools",
        help="run: command that starts riscv-tools for the generator",
    )
    p.add_argument(
        "--anchor",
        default="p1_rv32i",
        help="verify: profile that fixes the shift of the core term",
    )
    p.add_argument(
        "--output", help="verify: file to write the comparison (YAML)"
    )
    p.add_argument("--quartus-sh", default="quartus_sh")
    p.add_argument(
        "--stop-after",
        choices=["map", "fit"],
        default="map",
        help="run: last stage; fit also records what the fitter reports "
        "(the ratio between the fitter and the synthesis)",
    )
    p.add_argument("--only", help="run: comma list of profile ids")
    p.add_argument(
        "--keep", action="store_true", help="run: keep the work copies"
    )

    p = add_command(
        sub,
        cmd_check_fit,
        "check-fit",
        description="Fail when the fitter report of a compilation exceeds "
        "a resource of the board",
    )
    p.add_argument(
        "--reports", required=True, help="Directory with the *.fit.summary"
    )
    p.add_argument(
        "--board", required=True, help="board.yaml with the resources"
    )
