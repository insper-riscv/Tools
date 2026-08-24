"""Identify one JTAG connection and run this package's bundled .tcl scripts."""

import subprocess
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

    Parameters
    ----------
    cmd : list of str
        Argument list to execute (same shape as subprocess.run's
        first argument).
    **kw : Any
        Extra keyword arguments forwarded to subprocess.run (e.g. cwd,
        capture_output, text). check=True is always passed regardless
        of **kw.

    Returns
    -------
    subprocess.CompletedProcess
        The completed subprocess.

    Raises
    ------
    subprocess.CalledProcessError
        cmd exited non-zero.
    """
    print("+", " ".join(str(c) for c in cmd))
    # **kw's Any spread defeats subprocess.run's overload resolution
    # (its return type depends on the specific text/encoding/errors
    # combination passed) — cast to the shape run_tcl's callers
    # actually get back.
    return cast(
        "subprocess.CompletedProcess[Any]", subprocess.run(cmd, check=True, **kw)
    )


def run_tcl(
    link: JtagLink, script_name: str, *args: Any, capture: bool = False
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
    capture : bool, optional
        If True, captures stdout/stderr as text on the returned
        result (needed by callers that parse the script's output,
        e.g. mem_edit.read_words); if False, output streams straight
        to the console. Defaults to False.

    Returns
    -------
    subprocess.CompletedProcess
        The completed subprocess (see run).
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
    return run(cmd, capture_output=capture, text=capture)
