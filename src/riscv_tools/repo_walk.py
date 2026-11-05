"""Walk the files of a repository that belong to it.

The checks that read a whole repository (`tree_check`, `vhdl_style`)
share this walk, so they agree on what is part of the repository: it
leaves out hidden folders, build output, third-party code in `vendor`
and any folder that is a repository of its own (a submodule), whose
files are checked in its own repository. A submodule is recognized by
its path in `.gitmodules` (so a clone without `.git`, such as a copy
made by rsync, still leaves it out) and by a `.git` entry in the folder.
"""

import configparser
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml

_NOT_SOURCES = frozenset(
    {
        "build",
        "sim_build",
        "__pycache__",
        "node_modules",
        "output_files",
        "db",
        "incremental_db",
    }
)


def tree_config(root: Path) -> dict[str, Any]:
    """Read the `tree` section of the repository's `paths.yaml`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    dict of str to Any
        The section, or an empty mapping when the file or the section
        is absent.
    """
    manifest = root / "paths.yaml"
    if not manifest.is_file():
        return {}
    data = yaml.safe_load(manifest.read_text())
    if not isinstance(data, dict):
        return {}
    section = cast("dict[str, Any]", data).get("tree")
    if not isinstance(section, dict):
        return {}
    return cast("dict[str, Any]", section)


def submodule_paths(root: Path) -> frozenset[str]:
    """Read the submodule paths declared in the `.gitmodules` of a root.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    frozenset of str
        The paths, relative to the root and with `/` separators; empty
        when there is no `.gitmodules` or it cannot be read.
    """
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return frozenset()
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(gitmodules.read_text())
    except configparser.Error:
        return frozenset()
    return frozenset(
        Path(parser.get(section, "path")).as_posix().strip("/")
        for section in parser.sections()
        if parser.has_option(section, "path")
    )


def directories(root: Path, under: str = ".") -> Iterator[Path]:
    """Walk the folders of the repository that belong to it.

    Parameters
    ----------
    root : Path
        The repository root.
    under : str, optional
        The folder, relative to the root, where the walk starts; the
        root itself by default. Submodules are always matched against
        the root.

    Yields
    ------
    Path
        Each folder, below the starting folder.
    """
    modules = submodule_paths(root)
    for current, names, _ in os.walk(root / under):
        here = Path(current)
        names[:] = sorted(
            name
            for name in names
            if not name.startswith(".")
            and name not in _NOT_SOURCES
            and name != "vendor"
            and not (here / name / ".git").exists()
            and (here / name).relative_to(root).as_posix() not in modules
        )
        for name in names:
            yield here / name


def list_files(root: Path, suffix: str, under: str = ".") -> Iterator[Path]:
    """List the files with a suffix in the folders of the repository.

    Parameters
    ----------
    root : Path
        The repository root.
    suffix : str
        The file name ending, such as `.vhd`.
    under : str, optional
        The folder, relative to the root, where the listing starts; the
        root itself by default.

    Yields
    ------
    Path
        Each file found, including the ones in the starting folder.
    """
    start = root / under
    if not start.is_dir():
        return
    for folder in (start, *directories(root, under)):
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.name.endswith(suffix):
                yield entry
