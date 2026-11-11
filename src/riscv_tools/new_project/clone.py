"""Copy the template platform into the folder of the new one."""

import re
import shutil
from pathlib import Path

from riscv_tools.new_project.template import Template, rename_text, snake

_TEXT_SUFFIXES = {".yaml", ".vhd", ".S", ".ld", ".h", ".c", ".specs", ".py"}
_ENTITY = re.compile(r"^entity (\w+) is", re.MULTILINE | re.IGNORECASE)


def _file_name(name: str, old: str, new: str) -> str:
    """Rename a file that carries the platform's name.

    Parameters
    ----------
    name : str
        The file name.
    old : str
        Name of the template platform.
    new : str
        Name of the new platform.

    Returns
    -------
    str
        The name with the platform part replaced, in both spellings.
    """
    return name.replace(old, new).replace(snake(old), snake(new))


def _rename_entity(folder: Path, new: str) -> None:
    """Give the simulation top of the copy an entity of its own.

    Parameters
    ----------
    folder : Path
        Folder of the new platform.
    new : str
        Name of the new platform.
    """
    tops = sorted(folder.glob("*_sim_top.vhd"))
    if not tops:
        return
    found = _ENTITY.search(tops[0].read_text())
    if found is None:
        return
    entity = f"{snake(new)}_sim_test"
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix in _TEXT_SUFFIXES:
            text = path.read_text()
            if found[1] in text:
                path.write_text(text.replace(found[1], entity))


def copy_platform(repo: Path, template: Template, new: str) -> Path:
    """Copy the template's folder under the new name.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    template : Template
        The platform to copy.
    new : str
        Name of the new platform.

    Returns
    -------
    Path
        The new folder, from the repository root.

    Raises
    ------
    FileExistsError
        If the new folder already exists.
    """
    target = template.folder.parent / new
    if (repo / target).exists():
        raise FileExistsError(f"{target} already exists")
    shutil.copytree(repo / template.folder, repo / target)
    for path in sorted((repo / target).rglob("*"), reverse=True):
        renamed = path.with_name(_file_name(path.name, template.name, new))
        if path.is_file() and path.suffix in _TEXT_SUFFIXES:
            path.write_text(
                rename_text(
                    path.read_text(), template.name, new, template.board
                )
            )
        if renamed != path:
            path.rename(renamed)
    _rename_entity(repo / target, new)
    return target
