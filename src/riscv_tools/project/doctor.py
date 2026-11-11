"""Check that a project has what it needs to build and program."""

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.project.manifest import Manifest

TOOLS = ("quartus_sh", "quartus_pgm", "jtagconfig")
JTAG_TIMEOUT_S = 20
Which = Callable[[str], str | None]
Probe = Callable[[], str]


@dataclass(frozen=True)
class Check:
    """The result of one check.

    Parameters
    ----------
    name : str
        What was checked.
    ok : bool
        Whether it passed.
    detail : str
        What was found, or what to do about it.
    required : bool
        Whether a failure makes `project doctor` fail.
    """

    name: str
    ok: bool
    detail: str
    required: bool = True


def probe_jtag() -> str:
    """Ask `jtagconfig` for the cables and chips it sees.

    Returns
    -------
    str
        The text `jtagconfig` printed, or why it could not run.
    """
    try:
        done = subprocess.run(
            ["jtagconfig"],
            check=False,
            capture_output=True,
            text=True,
            timeout=JTAG_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"jtagconfig did not run: {error}"
    return (done.stdout + done.stderr).strip()


def check_files(project: Path, manifest: Manifest) -> list[Check]:
    """Check the files of the platform.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        The project.

    Returns
    -------
    list of Check
        One check per file the commands read.
    """
    repo = manifest.repo_path(project)
    names = ("platform.yaml", "config.yaml")
    return [
        Check(
            f"{manifest.platform}/{name}",
            (repo / manifest.platform / name).is_file(),
            "found"
            if (repo / manifest.platform / name).is_file()
            else "missing; create the project again",
        )
        for name in names
    ]


def check_quartus(which: Which | None = None) -> list[Check]:
    """Check that the Quartus tools are on the PATH.

    Parameters
    ----------
    which : Callable, optional
        Finds a program on the PATH; replaced in tests.

    Returns
    -------
    list of Check
        One check per tool.
    """
    find = which or shutil.which
    return [
        Check(
            tool,
            find(tool) is not None,
            find(tool)
            or "not on the PATH; start through ./rt with the Quartus "
            "mounted, or install it (see QUARTUS_ROOT)",
        )
        for tool in TOOLS
    ]


def board_idcode(repo: Path, board: str) -> str | None:
    """Read the IDCODE of the FPGA of a board from the catalog.

    Parameters
    ----------
    repo : Path
        The `Insper-RISC-V` checkout.
    board : str
        A board of the catalog.

    Returns
    -------
    str or None
        The IDCODE of the chain entry marked `fpga`, or None when the
        board file is missing or lists none.
    """
    path = repo / "boards" / board / "board.yaml"
    if not path.is_file():
        return None
    data = cast(dict[str, Any], yaml.safe_load(path.read_text()) or {})
    jtag = cast(dict[str, Any], data.get("jtag") or {})
    for entry in cast(list[dict[str, Any]], jtag.get("chain") or []):
        if entry.get("fpga"):
            return str(entry["idcode"]).upper()
    return None


def _cable_with(text: str, idcode: str) -> str | None:
    """Find the cable whose chain lists an IDCODE.

    Parameters
    ----------
    text : str
        The `jtagconfig` output.
    idcode : str
        The IDCODE to look for.

    Returns
    -------
    str or None
        The cable line (for example `1) USB-Blaster [1-2]`), or None
        when no cable lists the IDCODE.
    """
    cable = ""
    for line in text.splitlines():
        if line[:1].isdigit():
            cable = line.strip()
        elif idcode in line.upper():
            return cable
    return None


def check_cable(
    probe: Probe | None = None, idcode: str | None = None
) -> Check:
    """Check that the JTAG cable of the board is connected.

    Parameters
    ----------
    probe : Callable, optional
        Returns the `jtagconfig` text; replaced in tests.
    idcode : str, optional
        IDCODE of the FPGA of the board. With it, the check looks for
        the cable whose chain lists that chip, which matters on a
        computer with several boards; without it, any cable counts.

    Returns
    -------
    Check
        Passes when the cable is found; not required, since a project
        can be built without a board.
    """
    text = (probe or probe_jtag)()
    if idcode is not None:
        cable = _cable_with(text, idcode)
        found = cable is not None
        detail = (
            f"{cable} has {idcode}"
            if found
            else (
                f"no cable lists {idcode}; check the USB cable and the power "
                "of the board"
            )
        )
        return Check(f"JTAG cable ({idcode})", found, detail, required=False)
    seen = "USB-Blaster" in text and "Unable" not in text
    return Check(
        "JTAG cable",
        seen,
        text.splitlines()[0] if seen else (text or "no output"),
        required=False,
    )


def render(checks: list[Check]) -> str:
    """Write the report of the checks.

    Parameters
    ----------
    checks : list of Check
        The results.

    Returns
    -------
    str
        One line per check.
    """
    marks = {True: "ok     ", False: "FAILED "}
    return "\n".join(
        f"{marks[c.ok] if c.required or c.ok else 'warning'} "
        f"{c.name}: {c.detail}"
        for c in checks
    )


def passed(checks: list[Check]) -> bool:
    """Tell whether every required check passed.

    Parameters
    ----------
    checks : list of Check
        The results.

    Returns
    -------
    bool
        True when no required check failed.
    """
    return all(c.ok for c in checks if c.required)
