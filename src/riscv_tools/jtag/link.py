"""Identify one JTAG connection and run this package's bundled .tcl scripts."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from riscv_tools.proc import run_streaming

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

    Thin wrapper around riscv_tools.proc.run_streaming — see there for
    the streaming/classification rationale. Kept as its own function
    (rather than every call site importing run_streaming directly) so
    this module's own callers/docs keep referring to "jtag.link.run".

    Parameters
    ----------
    cmd : list of str
        Argument list to execute (same shape as subprocess.run's
        first argument).
    **kw : Any
        Extra keyword arguments forwarded to subprocess.Popen (e.g.
        cwd).

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
    return cast("subprocess.CompletedProcess[Any]", run_streaming(cmd, **kw))


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
