"""The subcommands of the fit check: calibrate and check-fit."""

import argparse
import shlex
import socket
import sys
import tempfile
from pathlib import Path

from riscv_tools import calibration, fit_estimate, quartus_reports
from riscv_tools.cli.common import project_root


def _log(message: str) -> None:
    """Print a progress message."""
    print(message, flush=True)


def cmd_calibrate(args: argparse.Namespace) -> None:
    """Implement `riscv-tools calibrate run|fit`.

    ``run`` measures the profiles of a family with the compile script of
    the project in synthesis only and writes one raw record per profile;
    ``fit`` reads the records and writes the calibration table of the
    family. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.action, args.profiles, args.raw,
        args.table, args.work_dir, args.lock, args.riscv_tools,
        args.quartus_sh, args.stop_after, args.only, args.keep and
        args.root.

    Returns
    -------
    None
        Prints the progress; exits with status 1 on a failed
        measurement or fit.
    """
    root = project_root(args)
    plan = calibration.load_profile_list(root / args.profiles)
    raw = root / args.raw
    try:
        if args.action == "run":
            settings = calibration.Settings(
                project=root,
                work_dir=Path(
                    args.work_dir
                    or Path(tempfile.gettempdir()) / "calibration"
                ),
                out_dir=raw,
                lock=Path(
                    args.lock
                    or Path(tempfile.gettempdir()) / f"quartus-{_host()}.lock"
                ),
                riscv_tools=tuple(shlex.split(args.riscv_tools)),
                quartus_sh=args.quartus_sh,
                keep=args.keep,
                stop_after=args.stop_after,
                log=_log,
            )
            only: list[str] = args.only.split(",") if args.only else []
            calibration.run_all(plan, settings, only)
            return
        content = calibration.fit_table(plan, calibration.load_records(raw))
        calibration.write_table(content, root / args.table)
    except (RuntimeError, ValueError) as error:
        print(f"calibrate: {error}", file=sys.stderr)
        sys.exit(1)
    error_pct = content["error"]
    print(
        f"calibration written: {args.table} (rms "
        f"{error_pct['rms_pct']}%, holdout max {error_pct['max_pct']}%)"
    )


def _host() -> str:
    """Name the machine for its lock file."""
    return socket.gethostname().split(".")[0]


def cmd_check_fit(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-fit`.

    Reads the fitter summary (and report) a compilation left and lists
    every resource over the capacity of the board at once (V14).
    Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.reports, args.board and
        args.root.

    Returns
    -------
    None
        Prints the findings; exits with status 1 when one is an error
        and with status 2 when the reports or the board are unreadable.
    """
    root = project_root(args)
    reports = root / args.reports
    try:
        summary = next(iter(sorted(reports.glob("*.fit.summary"))), None)
        report = next(iter(sorted(reports.glob("*.fit.rpt"))), None)
        usage = quartus_reports.parse_fit_report(
            report.read_text(encoding="utf-8") if report else "",
            summary.read_text(encoding="utf-8") if summary else None,
        )
        capacity = fit_estimate.load_capacity(root / args.board)
    except (OSError, ValueError, KeyError) as error:
        print(f"check-fit: {error}", file=sys.stderr)
        sys.exit(2)
    findings = fit_estimate.report_findings(usage, capacity)
    for finding in findings:
        print(f"FIT {finding.message}", file=sys.stderr)
    if any(item.severity == "E" for item in findings):
        sys.exit(1)
    print("fit OK: no resource over its capacity")
