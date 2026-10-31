"""Analyze the extra libraries and expand the paths of a simulation."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def expand_env(text: str) -> str:
    """Replace `$VAR` and `${VAR}` in text from the environment.

    Parameters
    ----------
    text : str
        A path or template from the config.

    Returns
    -------
    str
        text with every variable replaced.

    Raises
    ------
    SystemExit
        A variable is not set, naming it: GHDL would otherwise report a
        file it cannot find, far from the cause.
    """
    expanded = os.path.expandvars(text)
    unset = sorted(set(re.findall(r"\$\{?(\w+)\}?", expanded)))
    if unset:
        raise SystemExit(
            f"{text!r} uses an environment variable that is not set: "
            f"{', '.join(unset)}"
        )
    return expanded


def build_libraries(
    libraries: dict[str, list[str]],
    ghdl_std: str,
    ghdl_flags: list[str],
    libraries_dir: Path,
) -> None:
    """Analyze each VHDL library into libraries_dir, once per suite.

    cocotb_tools.runner builds every source into a single library, so a
    library a design instantiates by name (e.g. altera_mf) is analyzed
    here first and then found with `-P<libraries_dir>`, instead of once
    per test: altera_mf alone is 50 thousand lines.

    Parameters
    ----------
    libraries : dict of {str: list of str}
        {library name: source files, in dependency order}, with
        absolute paths: GHDL runs in libraries_dir.
    ghdl_std : str
        GHDL `--std=` value.
    ghdl_flags : list of str
        Extra GHDL arguments (sim.ghdl_flags).
    libraries_dir : Path
        Directory the analyzed libraries go into (created, and emptied
        first so a previous run's units do not linger).
    """
    if libraries_dir.exists():
        shutil.rmtree(libraries_dir)
    libraries_dir.mkdir(parents=True)

    for name, sources in libraries.items():
        print(f"Analyzing library {name} ({len(sources)} file(s))")
        subprocess.run(
            [
                "ghdl",
                "-a",
                f"--std={ghdl_std}",
                f"--work={name}",
                *ghdl_flags,
                *sources,
            ],
            cwd=libraries_dir,
            check=True,
            stdout=subprocess.DEVNULL,
        )


def extend_python_path(root: Path, entries: list[str]) -> None:
    """Put directories on the module search path, ahead of the rest.

    The simulation's test module is imported by a cocotb subprocess that
    inherits `sys.path` from this process, so a module is found only if
    its directory is on it.

    Parameters
    ----------
    root : Path
        The project root that relative entries are resolved against.
    entries : list of str
        Directories, relative to `root` (or absolute). Ones already on
        the path are left where they are.

    Returns
    -------
    None
        Inserts into `sys.path`.
    """
    for entry in entries:
        path = str((root / entry).resolve())
        if path not in sys.path:
            sys.path.insert(0, path)
