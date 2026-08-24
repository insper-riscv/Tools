import subprocess
from dataclasses import dataclass
from pathlib import Path

TCL_DIR = Path(__file__).resolve().parent / "tcl"


@dataclass(frozen=True)
class JtagLink:
    """Identifies one JTAG connection: which cable and which chip on it.

    Args:
        hardware_name: The "USB-Blaster [<bus>-<port>]" cable name,
            live-detected (see hardware.detect_jtag_hardware) rather
            than read from config — it drifts across reboots/hub
            renumbering.
        device_name: The target chip's JTAG identity string, from a
            project's config (`quartus.jtag_device`) — stable across
            reboots, unlike hardware_name.
    """

    hardware_name: str
    device_name: str


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    """Runs a subprocess, echoing the command line first.

    Args:
        cmd: Argument list to execute (same shape as
            subprocess.run's first argument).
        **kw: Extra keyword arguments forwarded to subprocess.run
            (e.g. cwd, capture_output, text). check=True is always
            passed regardless of **kw.

    Returns:
        The completed subprocess.CompletedProcess.

    Raises:
        subprocess.CalledProcessError: cmd exited non-zero.
    """
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def run_tcl(link: JtagLink, script_name: str, *args, capture: bool = False) -> subprocess.CompletedProcess:
    """Runs one of this package's bundled tcl/ scripts via quartus_stp,
    always passing (hardware_name, device_name) first, then *args.

    Args:
        link: Which JTAG cable/chip to run the script against.
        script_name: Filename of the .tcl script under this package's
            jtag/tcl/ directory (e.g. "write_full.tcl").
        *args: Extra positional arguments appended after
            (hardware_name, device_name) on the command line — each
            converted to str.
        capture: If True, captures stdout/stderr as text on the
            returned result (needed by callers that parse the
            script's output, e.g. mem_edit.read_words); if False,
            output streams straight to the console.

    Returns:
        The completed subprocess.CompletedProcess (see run).
    """
    script = TCL_DIR / script_name
    cmd = ["quartus_stp", "-t", str(script), link.hardware_name, link.device_name, *[str(a) for a in args]]
    return run(cmd, capture_output=capture, text=capture)
