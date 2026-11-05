"""Walk the files of a repository that belong to it.

The checks that read a whole repository (`tree_check`, `vhdl_style`)
share this walk, so they agree on what is part of the repository: it
leaves out hidden folders, build output, third-party code in `vendor`
and any folder that is a repository of its own (a submodule), whose
files are checked in its own repository.
"""

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


def directories(root: Path) -> Iterator[Path]:
    """Walk the folders of the repository that belong to it.

    Parameters
    ----------
    root : Path
        The repository root.

    Yields
    ------
    Path
        Each folder, below the root.
    """
    for current, names, _ in os.walk(root):
        here = Path(current)
        names[:] = sorted(
            name
            for name in names
            if not name.startswith(".")
            and name not in _NOT_SOURCES
            and name != "vendor"
            and not (here / name / ".git").exists()
        )
        for name in names:
            yield here / name


def list_files(root: Path, suffix: str) -> Iterator[Path]:
    """List the files with a suffix in the folders of the repository.

    Parameters
    ----------
    root : Path
        The repository root.
    suffix : str
        The file name ending, such as `.vhd`.

    Yields
    ------
    Path
        Each file found, including the ones in the root itself.
    """
    for folder in (root, *directories(root)):
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.name.endswith(suffix):
                yield entry
