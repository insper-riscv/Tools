"""Identify one JTAG connection and run this package's bundled .tcl scripts."""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

TCL_DIR = Path(__file__).resolve().parent / "tcl"


@dataclass(frozen=True)
class JtagLink:
    """Identify one JTAG connection: which cable and which chip on it.

    Attributes
    ----------
    hardware_name : str
        The "USB-Blaster [<bus>-<port>]" cable name, live-detected
        (see hardware.detect_jtag_hardware) rather than read from
        config — it drifts across reboots/hub renumbering.
    device_name : str
        The target chip's JTAG identity string, from a project's
        config (`quartus.jtag_device`) — stable across reboots, unlike
        hardware_name.
    """

    hardware_name: str
    device_name: str


def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[Any]:
    """Run a subprocess, echoing the command line first.

    Always captures stdout/stderr as text internally — regardless of
    what the caller passes for capture_output/text — and prints them
    straight through afterward either way, so a caller that never asked
    to capture still sees the same output on its own screen as before
    (just buffered until the process exits rather than streamed live).
    The point: a subprocess.CalledProcessError raised from here always
    carries real .stdout/.stderr text a caller can inspect (e.g. to
    tell "Can't scan JTAG chain" apart from other failures — see
    orchestrator.runner's hardware-failure classifier) — before this,
    any call site that left capture_output at its default (most of
    them) got a CalledProcessError with .stdout/.stderr both None,
    impossible to classify.

    Parameters
    ----------
    cmd : list of str
        Argument list to execute (same shape as subprocess.run's
        first argument).
    **kw : Any
        Extra keyword arguments forwarded to subprocess.run (e.g. cwd).
        check/capture_output/text are always forced regardless of what's
        passed here.

    Returns
    -------
    subprocess.CompletedProcess
        The completed subprocess — .stdout/.stderr are always text
        (never None), even for a caller that historically requested
        capture=False.

    Raises
    ------
    subprocess.CalledProcessError
        cmd exited non-zero — .stdout/.stderr are populated same as
        above.
    """
    print("+", " ".join(str(c) for c in cmd))
    kw.pop("capture_output", None)
    kw.pop("text", None)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        raise
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return cast("subprocess.CompletedProcess[Any]", result)


def run_tcl(
    link: JtagLink, script_name: str, *args: Any
) -> subprocess.CompletedProcess[Any]:
    """Run one of this package's bundled tcl/ scripts via quartus_stp.

    Always passes (hardware_name, device_name) first, then *args.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to run the script against.
    script_name : str
        Filename of the .tcl script under this package's jtag/tcl/
        directory (e.g. "write_full.tcl").
    *args : Any
        Extra positional arguments appended after (hardware_name,
        device_name) on the command line — each converted to str.

    Returns
    -------
    subprocess.CompletedProcess
        The completed subprocess (see run) — .stdout/.stderr are
        always text, whether or not the caller needs to parse them
        (e.g. mem_edit.read_words does; most callers just let run()
        print them through instead).
    """
    script = TCL_DIR / script_name
    cmd = [
        "quartus_stp",
        "-t",
        str(script),
        link.hardware_name,
        link.device_name,
        *[str(a) for a in args],
    ]
    return run(cmd)
