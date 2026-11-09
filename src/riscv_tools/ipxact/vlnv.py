"""The VLNV of a component: vendor, library, name and version.

The vendor is the domain of the project; the library is the short name
of the repository; the name is the entity; the version is the one of
the repository. Rule SCR 1.1 (IEEE Std 1685-2022, annex B) asks the
VLNV of every document to be unique, and the file name carries it.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.ipxact.model import ExtractError

VENDOR = "insper.edu.br"
LIBRARIES = {
    "Common-Components": "common",
    "Core": "core",
    "Memory": "memory",
    "Peripherals": "peripherals",
    "Insper-RISC-V": "top",
}


@dataclass(frozen=True)
class Vlnv:
    """The identifier of an IP-XACT document.

    Parameters
    ----------
    vendor : str
        The vendor domain.
    library : str
        The library, one per repository.
    name : str
        The document name.
    version : str
        The version of the document.
    """

    vendor: str
    library: str
    name: str
    version: str

    def file_name(self, kind: str) -> str:
        """Give the file name of a document of this VLNV.

        Parameters
        ----------
        kind : str
            The kind of document (`component`, `design`, ...).

        Returns
        -------
        str
            `<name>.<version>.<kind>.xml`.
        """
        return f"{self.name}.{self.version}.{kind}.xml"


def library_of(repository: str) -> str:
    """Give the library name of a repository."""
    return LIBRARIES.get(repository, repository.lower())


def repository_version(root: Path) -> str:
    """Read the version of a repository from its `pyproject.toml`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    str
        The `project.version` value.

    Raises
    ------
    ExtractError
        If the file or the version is missing.
    """
    manifest = root / "pyproject.toml"
    if not manifest.is_file():
        raise ExtractError(f"{manifest} not found: no version for the VLNV")
    version = (
        tomllib.loads(manifest.read_text()).get("project", {}).get("version")
    )
    if not isinstance(version, str):
        raise ExtractError(f"{manifest} has no project.version")
    return version
