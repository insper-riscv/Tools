"""List the VHDL files that the style guide covers.

The list is the files the project writes by hand: `src/**/*.vhd` and
`tests/vhdl/*.vhd`, without third-party code (`vendor/`), submodules
(`src/common`) and the files that `paths.yaml` names under
`tree.vhdl_style.exclude`. The top-levels of the board, in
`cyclone-v/`, are in the list but apart, because their names come
from the `.qsf` of Quartus.
"""

import fnmatch
from pathlib import Path
from typing import cast

from riscv_tools.repo_walk import list_files, tree_config

BOARD_FOLDER = "cyclone-v"
_TEST_PATH_PARTS = 3
_IP_MARKERS = ("megafunction wizard", "altera_mf")


def _extra_excludes(root: Path) -> list[str]:
    """Read the globs that `paths.yaml` adds to the exclusions.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of str
        The globs, empty when the repository names none.
    """
    section = tree_config(root).get("vhdl_style")
    if not isinstance(section, dict):
        return []
    listed = cast("dict[str, object]", section).get("exclude", [])
    if not isinstance(listed, list):
        return []
    return [str(glob) for glob in cast("list[object]", listed)]


def is_generated_ip(relative: str, text: str) -> bool:
    """Tell a Quartus IP from a file written by hand.

    Parameters
    ----------
    relative : str
        The path relative to the repository root, in POSIX form.
    text : str
        The content of the file.

    Returns
    -------
    bool
        True when the file sits in a `cyclone-v` folder or instantiates
        a Quartus megafunction (`altera_mf`).
    """
    return is_board_file(relative) or has_ip_marker(text)


def has_ip_marker(text: str) -> bool:
    """Tell whether a file says it is a Quartus megafunction.

    Parameters
    ----------
    text : str
        The content of the file.

    Returns
    -------
    bool
        True when the text mentions `altera_mf` or the wizard.
    """
    lowered = text.lower()
    return any(marker in lowered for marker in _IP_MARKERS)


def is_board_file(relative: str) -> bool:
    """Tell a top-level of the board from the rest of the sources.

    Parameters
    ----------
    relative : str
        The path relative to the repository root, in POSIX form.

    Returns
    -------
    bool
        True when a folder of the path is `cyclone-v`, in any case.
    """
    folders = relative.split("/")[:-1]
    return BOARD_FOLDER in {part.lower() for part in folders}


def _in_scope(relative: str) -> bool:
    """Tell whether a path is one the style guide covers.

    Parameters
    ----------
    relative : str
        The path relative to the repository root, in POSIX form.

    Returns
    -------
    bool
        True for `src/**/*.vhd` and `tests/vhdl/*.vhd`.
    """
    parts = relative.split("/")
    return parts[0] == "src" or (
        len(parts) == _TEST_PATH_PARTS and parts[:2] == ["tests", "vhdl"]
    )


def vhdl_files(root: Path, board: bool = False) -> list[str]:
    """List the VHDL files the style guide covers.

    Parameters
    ----------
    root : Path
        The repository root.
    board : bool, optional
        True for the top-levels of the board (in `cyclone-v/`), False
        for all the other files, by default False.

    Returns
    -------
    list of str
        The paths relative to the root, in POSIX form and in order.
    """
    excludes = _extra_excludes(root)
    found: list[str] = []
    for path in list_files(root, ".vhd"):
        relative = path.relative_to(root).as_posix()
        if (
            not _in_scope(relative)
            or is_board_file(relative) != board
            or any(fnmatch.fnmatch(relative, glob) for glob in excludes)
        ):
            continue
        found.append(relative)
    return found
