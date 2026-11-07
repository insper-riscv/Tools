"""The subcommands `board scan`, `select`, `lock` and `doctor`."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from riscv_tools.board import (
    BoardBusyError,
    BoardError,
    BoardLock,
    CableReport,
    scan,
)
from riscv_tools.board.doctor import FAIL, Check, missing_tool, run_doctor
from riscv_tools.board.inventory import USER_FILE, dump_inventory
from riscv_tools.board.register import register
from riscv_tools.board.runtime import (
    boards_directories,
    build_environment,
    platform_choice,
)
from riscv_tools.board.select import (
    Environment,
    Request,
    Selection,
    present,
    select_board,
)
from riscv_tools.board.usb import list_cable_users, read_usb
from riscv_tools.cli.common import project_root


def _environment(args: argparse.Namespace) -> Environment:
    """Read the host the way the options say."""
    directories = boards_directories(args.boards_dir, project_root(args))
    inventory = Path(args.inventory) if args.inventory else None
    try:
        return build_environment(directories, inventory, args.host)
    except BoardError as error:
        _fail(error)
        raise


def _request(args: argparse.Namespace) -> Request:
    """Build the selection request from the options."""
    platform = Path(args.platform) if args.platform else None
    board, allowed = platform_choice(platform)
    return Request(
        cable=args.cable,
        board_id=args.board_id,
        board=args.board,
        platform_board=board,
        allowed=allowed,
        free=args.free,
    )


def _print_selection(selection: Selection, as_json: bool) -> None:
    """Print one selection."""
    data = selection.as_dict()
    if as_json:
        print(json.dumps(data, indent=2))
        return
    for key, value in data.items():
        if key != "warnings":
            print(f"{key}: {value}")
    for warning in selection.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _fail(error: BoardError) -> None:
    """Report a board error and exit."""
    prefix = f"case {error.case}: " if error.case else ""
    print(f"error: {prefix}{error}", file=sys.stderr)
    sys.exit(3 if isinstance(error, BoardBusyError) else 2)


def _scan_json(reports: list[CableReport]) -> str:
    """Write the scan as JSON."""
    return json.dumps(
        [
            {
                "cable": r.cable.name,
                "port": r.port,
                "chain": [d.idcode for d in r.cable.devices],
                "boards": list(r.boards),
                "inventory_id": r.entry.id if r.entry else None,
                "problem": r.problem,
            }
            for r in reports
        ],
        indent=2,
    )


def _print_scan(reports: list[CableReport]) -> None:
    """Print the scan as text, one block per cable."""
    for report in reports:
        chain = " ".join(d.idcode for d in report.cable.devices) or "-"
        known = ", ".join(report.boards) or "unknown"
        entry = report.entry.id if report.entry else "-"
        print(f"{report.cable.name}  port={report.port}  chain={chain}")
        print(f"  board: {known}  inventory: {entry}")
        if report.problem:
            print(f"  problem: {report.problem}")


def _save_inventory(
    args: argparse.Namespace, env: Environment, reports: list[CableReport]
) -> None:
    """Record the certain cables in the inventory file."""
    assign = dict(a.split("=", 1) for a in args.assign)
    saved, notes = register(env.inventory, reports, assign)
    default = USER_FILE.expanduser()
    target = Path(args.inventory) if args.inventory else default
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_inventory(saved), encoding="utf-8")
    print(f"inventory saved: {target}")
    for note in notes:
        print(f"not saved: {note}", file=sys.stderr)


def cmd_board_scan(args: argparse.Namespace) -> None:
    """Implement `riscv-tools board scan`.

    Lists every cable with its chain, its USB port, the boards it can
    be and the inventory entry of its port; with --save records the
    cables that are certain in the inventory of the host.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: boards_dir, inventory, host, save,
        assign, json.
    """
    env = _environment(args)
    reports = scan(env.cables, env.boards, env.inventory, env.resolve_port)
    if args.json:
        print(_scan_json(reports))
    else:
        _print_scan(reports)
    if args.save:
        _save_inventory(args, env, reports)


def cmd_board_select(args: argparse.Namespace) -> None:
    """Implement `riscv-tools board select`.

    Chooses the board and cable by the precedence --cable,
    --board-id, --board, the `board:` of the platform, auto; with
    --all lists every present board of the request instead.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: the selection options, json, all.
    """
    env = _environment(args)
    request = _request(args)
    try:
        if args.all:
            name = request.board or request.platform_board
            wanted = {name} if name and name != "auto" else None
            found = present(env, wanted)
            print(json.dumps([s.as_dict() for s in found], indent=2))
            return
        _print_selection(select_board(env, request), args.json)
    except BoardError as error:
        _fail(error)


def _hold(selection: Selection) -> int:
    """Print the selection, then keep the lock until stdin closes."""
    print(json.dumps(selection.as_dict()), flush=True)
    sys.stdin.read()
    return 0


def _run_command(selection: Selection, command: list[str]) -> int:
    """Run the command of a lock, telling it which board it holds."""
    env = dict(os.environ)
    env["RISCV_TOOLS_CABLE"] = selection.cable
    env["RISCV_TOOLS_BOARD"] = selection.board
    return subprocess.run(command, env=env, check=False).returncode


def cmd_board_lock(args: argparse.Namespace) -> None:
    """Implement `riscv-tools board lock`.

    Selects the board, takes its lock with the owner recorded, and
    holds it while the command after `--` runs, or with --hold until
    the standard input closes (a runner keeps it open for its session).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: the selection options, wait, hold,
        command.
    """
    env = _environment(args)
    command: list[str] = list(args.lock_command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command and not args.hold:
        sys.exit("board lock needs a command after `--`, or --hold")
    code = 0
    try:
        selection = select_board(env, _request(args))
        started = time.monotonic()
        with BoardLock(selection.lock_file, args.wait):
            if time.monotonic() - started > 1:
                print(
                    f"waited {time.monotonic() - started:.0f} s",
                    file=sys.stderr,
                )
            code = (
                _hold(selection)
                if args.hold
                else _run_command(selection, command)
            )
    except BoardError as error:
        _fail(error)
    sys.exit(code)


def _doctor_checks(args: argparse.Namespace) -> list[Check]:
    """Run the checks, or say why they cannot run."""
    if shutil.which("jtagconfig") is None:
        return [missing_tool()]
    try:
        env = _environment(args)
    except subprocess.CalledProcessError as error:
        return [Check("jtagconfig", FAIL, f"failed: {error}")]
    return run_doctor(env, read_usb(), list_cable_users())


def cmd_board_doctor(args: argparse.Namespace) -> None:
    """Implement `riscv-tools board doctor`.

    Runs the checks of cable, chain, processes and special boards, and
    prints what is missing; changes nothing. Exits 1 on a failure.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: boards_dir, inventory, host, json.
    """
    checks = _doctor_checks(args)
    if args.json:
        print(json.dumps([c.__dict__ for c in checks], indent=2))
    for check in [] if args.json else checks:
        print(f"[{check.level}] {check.name}: {check.detail}")
        if check.hint:
            print(f"       -> {check.hint}")
    sys.exit(1 if any(c.level == FAIL for c in checks) else 0)
