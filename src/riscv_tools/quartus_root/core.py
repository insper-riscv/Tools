"""Locate the Quartus installation and make its tools reachable.

The Quartus Prime Lite is installed in `/opt/altera_lite` (see the
`QUARTUS_INSTALL.md` of the Infra), one folder per version. Two
environment variables move it without touching a file.
"""

import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path

ROOT_VAR = "QUARTUS_ROOT"
VERSION_VAR = "QUARTUS_VERSION"
DEFAULT_ROOT = "/opt/altera_lite"
DEFAULT_VERSION = "25.1std"
_BIN = Path("quartus") / "bin"


def bin_dir(env: Mapping[str, str]) -> Path:
    """Give the folder of the Quartus programs.

    Parameters
    ----------
    env : mapping of {str: str}
        The environment; `QUARTUS_ROOT` is the folder that holds the
        versions and `QUARTUS_VERSION` picks one of them.

    Returns
    -------
    Path
        `<root>/<version>/quartus/bin`, with `/opt/altera_lite` and
        `25.1std` for what the environment leaves out or empty.
    """
    root = env.get(ROOT_VAR) or DEFAULT_ROOT
    version = env.get(VERSION_VAR) or DEFAULT_VERSION
    return Path(root) / version / _BIN


def prepend_to_path(env: MutableMapping[str, str] | None = None) -> bool:
    """Add the Quartus programs to the `PATH` of an environment.

    A `QUARTUS_ROOT` that the person set goes to the front, so it wins
    over a Quartus the `PATH` already has. The default folder goes to
    the end, so it only serves when nothing else provides the programs.

    Parameters
    ----------
    env : mutable mapping of {str: str}, optional
        The environment to change, by default `os.environ`.

    Returns
    -------
    bool
        True when the folder exists and was added; False when it does
        not exist or the `PATH` already lists it.
    """
    target = os.environ if env is None else env
    folder = str(bin_dir(target))
    if not Path(folder).is_dir():
        return False
    entries = [e for e in target.get("PATH", "").split(os.pathsep) if e]
    if folder in entries:
        return False
    chosen = bool(target.get(ROOT_VAR))
    ordered = [folder, *entries] if chosen else [*entries, folder]
    target["PATH"] = os.pathsep.join(ordered)
    return True
