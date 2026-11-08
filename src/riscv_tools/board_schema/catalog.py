"""Find and read the files of the board catalog.

The catalog lives in two places. The boards and the families are in the
`boards/` folder of the repository that owns the platforms, and the
chips are in the `chips/` folder of the memory repository, which is the
owner of the controllers that read their timings. The chip files name
their base chip with `extends: <chip>`, the same key the config files
use, read by the same code.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from riscv_tools.board_schema.board import parse_board
from riscv_tools.board_schema.chip import parse_chip
from riscv_tools.board_schema.family import parse_family
from riscv_tools.board_schema.fields import SchemaError
from riscv_tools.board_schema.model import Board, Chip, Family, Pin
from riscv_tools.board_schema.pins import conflict_pins, parse_pins
from riscv_tools.config_files import read_with_bases

NON_BOARD_FOLDERS = frozenset({"families", "calibration"})


class NotFoundError(LookupError):
    """A board, family or chip that the catalog does not have.

    Parameters
    ----------
    kind : str
        `board`, `family` or `chip`.
    name : str
        What was asked for.
    known : list of str
        What the catalog has.
    """

    def __init__(self, kind: str, name: str, known: list[str]) -> None:
        """Keep what was asked and what exists.

        Parameters
        ----------
        kind : str
            `board`, `family` or `chip`.
        name : str
            What was asked for.
        known : list of str
            What the catalog has.
        """
        super().__init__(f"{kind} '{name}' not found")
        self.kind = kind
        self.name = name
        self.known = known


def _chip_base(path: Path, ref: str) -> Path:
    """Name the file of the chip that a chip extends.

    Parameters
    ----------
    path : Path
        The chip file that holds the `extends` key.
    ref : str
        The name of the base chip.

    Returns
    -------
    Path
        The file of the base chip, next to this one.
    """
    return path.parent / f"{ref}.yaml"


def _names(folder: Path) -> list[str]:
    """List the YAML files of a folder by name.

    Parameters
    ----------
    folder : Path
        The folder.

    Returns
    -------
    list of str
        The stems, sorted; empty when the folder does not exist.
    """
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.yaml"))


def _yaml(path: Path) -> Any:
    """Read a YAML file.

    Parameters
    ----------
    path : Path
        The file.

    Returns
    -------
    Any
        The parsed content.

    Raises
    ------
    SchemaError
        If the file is not valid YAML.
    """
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise SchemaError([f"{path.name}: invalid YAML ({error})"]) from error


@dataclass(frozen=True)
class Catalog:
    """The folders of the board catalog.

    Parameters
    ----------
    boards : Path
        The `boards/` folder: a folder per board, `families/` and
        `calibration/`.
    chips : Path
        The `chips/` folder.
    """

    boards: Path
    chips: Path

    @classmethod
    def for_root(cls, root: Path) -> Catalog:
        """Locate the catalog from the root of a project.

        Parameters
        ----------
        root : Path
            The project root: the repository of the platforms, which
            mounts the memory repository as `Memory`, or the memory
            repository itself.

        Returns
        -------
        Catalog
            The folders; a `Memory/chips` folder wins over `chips`.
        """
        mounted = root / "Memory" / "chips"
        return cls(
            root / "boards", mounted if mounted.is_dir() else root / "chips"
        )

    def board_names(self) -> list[str]:
        """List the boards of the catalog.

        Returns
        -------
        list of str
            The folders that hold a `board.yaml`, sorted.
        """
        if not self.boards.is_dir():
            return []
        return sorted(
            folder.name
            for folder in self.boards.iterdir()
            if folder.name not in NON_BOARD_FOLDERS
            and (folder / "board.yaml").is_file()
        )

    def family_names(self) -> list[str]:
        """List the families of the catalog.

        Returns
        -------
        list of str
            The family files, sorted.
        """
        return _names(self.boards / "families")

    def chip_names(self) -> list[str]:
        """List the chips of the catalog.

        Returns
        -------
        list of str
            The chip files, sorted.
        """
        return _names(self.chips)

    def board_folder(self, name: str) -> Path:
        """Give the folder of a board.

        Parameters
        ----------
        name : str
            The board.

        Returns
        -------
        Path
            The folder.

        Raises
        ------
        NotFoundError
            If the board is not in the catalog.
        """
        if name not in self.board_names():
            raise NotFoundError("board", name, self.board_names())
        return self.boards / name

    def load_board(self, name: str) -> Board:
        """Read a board.

        Parameters
        ----------
        name : str
            The board.

        Returns
        -------
        Board
            The board.

        Raises
        ------
        NotFoundError
            If the board is not in the catalog.
        SchemaError
            If the file does not follow the schema.
        """
        path = self.board_folder(name) / "board.yaml"
        board = parse_board(_yaml(path), f"board {name}")
        if board.board != name:
            raise SchemaError(
                [f"board {name}: field board is '{board.board}'"]
            )
        return board

    def load_pins(self, name: str, board: Board) -> list[Pin]:
        """Read the pins file of a board.

        Parameters
        ----------
        name : str
            The board.
        board : Board
            The board, which names its pins file.

        Returns
        -------
        list of Pin
            The signals.

        Raises
        ------
        SchemaError
            If the file is missing or does not follow the schema.
        """
        path = self.board_folder(name) / board.pins
        if not path.is_file():
            raise SchemaError(
                [f"board {name}: pins file {board.pins} not found"]
            )
        return parse_pins(_yaml(path), f"pins {name}")

    def load_conflicts(self, name: str, board: Board) -> set[str]:
        """Read the pins a board declares as shared by several signals.

        Parameters
        ----------
        name : str
            The board.
        board : Board
            The board, which names its pins file.

        Returns
        -------
        set of str
            The pins of `conflicts` in the pins file.

        Raises
        ------
        SchemaError
            If the pins file is not valid YAML.
        """
        path = self.board_folder(name) / board.pins
        return conflict_pins(_yaml(path))

    def load_family(self, name: str) -> Family:
        """Read a family.

        Parameters
        ----------
        name : str
            The family.

        Returns
        -------
        Family
            The family.

        Raises
        ------
        NotFoundError
            If the family is not in the catalog.
        SchemaError
            If the file does not follow the schema.
        """
        if name not in self.family_names():
            raise NotFoundError("family", name, self.family_names())
        path = self.boards / "families" / f"{name}.yaml"
        family = parse_family(_yaml(path), f"family {name}")
        if family.family != name:
            raise SchemaError(
                [f"family {name}: field family is '{family.family}'"]
            )
        return family

    def load_chip(self, name: str) -> Chip:
        """Read a chip, with its `extends` chain resolved.

        Parameters
        ----------
        name : str
            The chip.

        Returns
        -------
        Chip
            The chip.

        Raises
        ------
        NotFoundError
            If the chip is not in the catalog.
        SchemaError
            If the file does not follow the schema.
        """
        if name not in self.chip_names():
            raise NotFoundError("chip", name, self.chip_names())
        path = self.chips / f"{name}.yaml"
        try:
            merged = read_with_bases(path, _chip_base)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise SchemaError([f"chip {name}: {error}"]) from error
        chip = parse_chip(merged, f"chip {name}")
        if chip.chip != name:
            raise SchemaError([f"chip {name}: field chip is '{chip.chip}'"])
        return chip
