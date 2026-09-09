"""Rotate and tee a run's full console output into a persistent per-kind log history.

Every `riscv-tools run/sim/certify` invocation prints a lot (JTAG
reload/poll progress, GHDL/cocotb build+run output, quartus_sh/
quartus_pgm's own streamed output — see proc.run_streaming) that's
otherwise gone the moment the terminal scrolls past it or the session
ends. This module makes each of those three subcommands write
everything to <root>/<run_log.logs_dir>/<kind>/latest.log too (kept
out of git — see a project's own .gitignore), so there's always a
`tail -f` target for the run in progress plus a rotated history of
every run before it, without needing a wrapper script or a manual
`| tee` at every call site.
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
# started at (not, say, whenever this rotation happened to run) —
# nothing recorded this before this module existed.
_START_LINE_RE = re.compile(r"^# run started (\S+)\s*$")
# Filesystem-safe (no ':') and sortable — used for the archived
# filename, independent of the ISO-8601 form the header line itself
# uses (kept human-readable there since nothing parses it back except
# this same regex).
_FS_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def _rotate(latest: Path) -> Path | None:
    """Archive an existing latest.log under its own recorded start timestamp.

    Parameters
    ----------
    latest : Path
        Path to a kind's latest.log — may or may not exist.

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
    except (OSError, ValueError):
        stamp = None

    if stamp is None:
        # No (or unparsable) recorded start line — e.g. a latest.log
        # left over from before this module existed, or one from a
        # run that got killed before write_text() below ever ran.
        # Falls back to the file's own last-modified time so it's
        # still archived under SOME timestamp instead of being
        # silently overwritten by the new latest.log about to be
        # created.
        stamp = datetime.datetime.fromtimestamp(latest.stat().st_mtime).strftime(
            _FS_TIMESTAMP_FMT
        )

    target = latest.with_name(f"{stamp}.log")
    suffix = 1
    while target.exists():
        # Two runs starting within the same second — astronomically
        # unlikely for a human-triggered CLI, but a suffix is cheap
        # insurance against clobbering one run's history with another's.
        target = latest.with_name(f"{stamp}_{suffix}.log")
        suffix += 1

    latest.rename(target)
    return target


def start(root: Path, kind: str, logs_dir: str = "logs") -> Path:
    """Rotate a kind's latest.log, start a fresh one, and tee this process onto it.

    Meant to be called once, near the top of a CLI subcommand
    (cmd_run/cmd_sim/cmd_certify) — everything printed for the rest of
    the process, by this code or any subprocess it spawns (quartus_sh,
    quartus_pgm, GHDL via cocotb, ...), ends up in both the real
    terminal and the returned log file, the same way a shell's own
    `... 2>&1 | tee file` would, but without needing the caller (or
    CI) to remember to invoke one. Implemented via os.dup2 onto an
    actual `tee` subprocess rather than reassigning sys.stdout/stderr
    in Python, specifically so it also catches output from any child
    process that inherits this process' file descriptors directly
    (most subprocess tooling does, unless explicitly captured) — a
    pure Python-level stream swap would miss those.

    Not meant to be undone within the same process: a `riscv-tools`
    invocation is a single one-shot subcommand, so there's nothing to
    "restore" stdout/stderr to before the process exits anyway.

    Parameters
    ----------
    root : Path
        The consuming project's root directory.
    kind : str
        Which log history this run belongs to — by convention
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
    tee = subprocess.Popen(["tee", "-a", str(latest)], stdin=subprocess.PIPE)
    tee_stdin = cast(IO[bytes], tee.stdin)
    os.dup2(tee_stdin.fileno(), sys.stdout.fileno())
    os.dup2(tee_stdin.fileno(), sys.stderr.fileno())

    return latest
