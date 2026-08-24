import subprocess
from dataclasses import dataclass
from pathlib import Path

TCL_DIR = Path(__file__).resolve().parent / "tcl"


@dataclass(frozen=True)
class JtagLink:
    """Identifies one JTAG connection: which cable (hardware_name,
    live-detected — see hardware.py) and which chip on it
    (device_name, from a project's config: quartus.jtag_device)."""

    hardware_name: str
    device_name: str


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def run_tcl(link: JtagLink, script_name: str, *args, capture: bool = False) -> subprocess.CompletedProcess:
    """Runs one of this package's bundled tcl/ scripts via quartus_stp,
    always passing (hardware_name, device_name) first, then *args."""
    script = TCL_DIR / script_name
    cmd = ["quartus_stp", "-t", str(script), link.hardware_name, link.device_name, *[str(a) for a in args]]
    return run(cmd, capture_output=capture, text=capture)
