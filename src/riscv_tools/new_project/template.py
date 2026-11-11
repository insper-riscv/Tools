"""Find the platform a new project starts from, and rename its text."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

CALIBRATION = "calibration"
TOP_PREFIX = "Insper-RISC-V/"
CREATED_MARK = "created by `riscv-tools new-project`"


@dataclass(frozen=True)
class Template:
    """The platform a new one is copied from.

    Parameters
    ----------
    folder : Path
        Folder of the platform, from the repository root.
    board : str
        The board it is built on.
    top : str
        Its `top` component in `paths.yaml`.
    """

    folder: Path
    board: str
    top: str

    @property
    def name(self) -> str:
        """Name of the platform: the name of its folder."""
        return self.folder.name


def snake(name: str) -> str:
    """Turn a platform name into its VHDL form.

    Parameters
    ----------
    name : str
        Name with hyphens.

    Returns
    -------
    str
        The same name with underscores.
    """
    return name.replace("-", "_")


def find_template(repo: Path, board: str) -> Template:
    """Pick the platform that is built on a board.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    board : str
        A board of the catalog.

    Returns
    -------
    Template
        The one platform outside `calibration/` that lists the board
        and names a `top`.

    Raises
    ------
    ValueError
        If no platform, or more than one, fits the board.
    """
    found: list[Template] = []
    for path in sorted((repo / "src").glob("*/*/platform.yaml")):
        if path.parts[-3] == CALIBRATION:
            continue
        text = path.read_text()
        data = yaml.safe_load(text)
        if CREATED_MARK in text or not isinstance(data, dict):
            continue
        fields = cast(dict[str, Any], data)
        if board in fields.get("boards", []) and fields.get("top"):
            folder = path.parent.relative_to(repo)
            found.append(Template(folder, board, str(fields["top"])))
    if len(found) != 1:
        names = ", ".join(t.name for t in found) or "none"
        raise ValueError(
            f"board {board!r} needs exactly one platform to start from; "
            f"found: {names}"
        )
    return found[0]


def rename_text(text: str, old: str, new: str, board: str) -> str:
    """Rename a platform inside the text of one of its files.

    Parameters
    ----------
    text : str
        The text.
    old : str
        Name of the template platform.
    new : str
        Name of the new platform.
    board : str
        The board, whose name stays where a project name has it.

    Returns
    -------
    str
        The text with the platform's folder, VHDL names and project
        names changed.
    """
    old_us, new_us = snake(old), snake(new)
    text = re.sub(
        rf"(src/[\w-]+/){re.escape(old)}(?![\w-])", rf"\1{new}", text
    )
    text = re.sub(rf"\b{re.escape(old_us)}(?=_)", new_us, text)
    text = re.sub(rf"(?<![\w-]){re.escape(old)}(?=_sim_top)", new, text)
    return re.sub(
        rf"(?<=build/){re.escape(old)}(?=-{re.escape(board)}\b)", new, text
    )
