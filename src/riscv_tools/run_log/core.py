"""Rotate and tee a run's console output into a per-kind history.

Each `riscv-tools run`, `sim` and `certify` invocation also writes
everything it prints to <root>/<run_log.logs_dir>/<kind>/latest.log and
archives the previous log, so a run in progress can be followed with
`tail -f` and earlier runs stay available.
"""

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import IO, cast

# Written as latest.log's very first line by start() below, and read
# back by _rotate() the NEXT time start() runs for the same kind, so a
# stale latest.log can be archived under the timestamp it actually
# started at (not, say, whenever this rotation happened to run);
# nothing recorded this before this module existed.
_START_LINE_RE = re.compile(r"^# run started (\S+)\s*$")
# Filesystem-safe (no ':') and sortable, used for the archived
# filename, independent of the ISO-8601 form the header line itself
# uses (kept human-readable there since nothing parses it back except
# this same regex).
_FS_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def _rotate(latest: Path) -> Path | None:
    """Archive an existing latest.log under its recorded timestamp.

    Parameters
    ----------
    latest : Path
        Path to a kind's latest.log, may or may not exist.

    Returns
    -------
    Path or None
        The archived file's new path, or None if latest didn't exist
        (nothing to rotate).
    """
    if not latest.is_file():
        return None

    stamp = None
    try:
        with latest.open(encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
        match = _START_LINE_RE.match(first_line)
        if match:
            stamp = datetime.datetime.fromisoformat(match.group(1)).strftime(
                _FS_TIMESTAMP_FMT
            )
    except OSError, ValueError:
        stamp = None

    if stamp is None:
        stamp = datetime.datetime.fromtimestamp(
            latest.stat().st_mtime
        ).strftime(_FS_TIMESTAMP_FMT)

    target = latest.with_name(f"{stamp}.log")
    suffix = 1
    while target.exists():
        target = latest.with_name(f"{stamp}_{suffix}.log")
        suffix += 1

    latest.rename(target)
    return target


def _spawn_tee(latest: Path) -> subprocess.Popen[bytes]:
    """Start the tee process that appends the run output to latest.

    The process outlives this call on purpose, so it is returned
    instead of being managed by a with block.

    Parameters
    ----------
    latest : Path
        The log file tee appends to.

    Returns
    -------
    subprocess.Popen
        The running tee, with a pipe on its stdin.
    """
    return subprocess.Popen(["tee", "-a", str(latest)], stdin=subprocess.PIPE)


def start(root: Path, kind: str, logs_dir: str = "logs") -> Path:
    """Rotate a kind's latest.log, start a new one and tee onto it.

    Call it once, near the top of a CLI subcommand. Everything printed
    for the rest of the process, including the output of subprocesses,
    goes to both the terminal and the returned log file, like `2>&1 |
    tee file`. It duplicates the file descriptors onto a `tee`
    subprocess instead of reassigning sys.stdout, so child processes
    that inherit the descriptors are captured too. It is not undone
    within the process.

    Parameters
    ----------
    root : Path
        The consuming project's root directory.
    kind : str
        Which log history this run belongs to, by convention
        "real" (cmd_run), "sim" (cmd_sim), or "certification"
        (cmd_certify), one subdirectory each under logs_dir, but any
        string is accepted (just becomes that subdirectory's name).
    logs_dir : str, optional
        Path (relative to root) holding one subdirectory per kind
        (run_log.logs_dir in config.yaml, default "logs").

    Returns
    -------
    Path
        Path to the fresh <root>/<logs_dir>/<kind>/latest.log this
        run's output is now being written to (already contains this
        function's own one-line header by the time it returns).
    """
    kind_dir = Path(root) / logs_dir / kind
    kind_dir.mkdir(parents=True, exist_ok=True)

    latest = kind_dir / "latest.log"
    archived = _rotate(latest)
    if archived is not None:
        print(f"run_log: archived previous {kind} run as {archived.name}")

    started_at = datetime.datetime.now().astimezone().isoformat()
    latest.write_text(f"# run started {started_at}\n")
    print(f"run_log: this run's full output is also being written to {latest}")

    sys.stdout.flush()
    sys.stderr.flush()
    tee_stdin = cast(IO[bytes], _spawn_tee(latest).stdin)
    os.dup2(tee_stdin.fileno(), sys.stdout.fileno())
    os.dup2(tee_stdin.fileno(), sys.stderr.fileno())

    return latest
