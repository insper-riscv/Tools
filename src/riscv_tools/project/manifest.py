"""The file that tells the commands which project they work on."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.new_project.naming import check_slug

PROJECT_FILE = "project.yaml"


@dataclass(frozen=True)
class Manifest:
    """What a project folder remembers about itself.

    Parameters
    ----------
    name : str
        Name of the project as the person typed it.
    slug : str
        Identifier derived from the name; it names the platform, the
        folder and the files.
    board : str
        Board of the catalog the platform is built on.
    repo : str
        Folder of the `Insper-RISC-V` checkout, from the project.
    platform : str
        Folder of the platform, from the checkout.
    """

    name: str
    slug: str
    board: str
    repo: str
    platform: str

    def repo_path(self, project: Path) -> Path:
        """Locate the checkout.

        Parameters
        ----------
        project : Path
            The project folder.

        Returns
        -------
        Path
            The `Insper-RISC-V` checkout.
        """
        return project / self.repo

    def config_path(self) -> str:
        """Name the `config.yaml` of the platform, from the checkout.

        Returns
        -------
        str
            The path of the file.
        """
        return f"{self.platform}/config.yaml"


def write_manifest(project: Path, manifest: Manifest) -> Path:
    """Write the manifest of a project.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        What to write.

    Returns
    -------
    Path
        The file that was written.
    """
    path = project / PROJECT_FILE
    fields = {
        "name": manifest.name,
        "slug": manifest.slug,
        "board": manifest.board,
        "repo": manifest.repo,
        "platform": manifest.platform,
    }
    path.write_text(
        yaml.safe_dump(fields, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def read_manifest(path: Path) -> Manifest:
    """Read a manifest.

    Parameters
    ----------
    path : Path
        The `project.yaml`.

    Returns
    -------
    Manifest
        The fields of the file.

    Raises
    ------
    ValueError
        If the file is not a mapping or lacks a field.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    fields = cast(dict[str, Any], data)
    missing = [
        k for k in ("name", "board", "repo", "platform") if k not in fields
    ]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    slug = check_slug(str(fields.get("slug", fields["name"])))
    return Manifest(
        str(fields["name"]),
        slug,
        str(fields["board"]),
        str(fields["repo"]),
        str(fields["platform"]),
    )


def find_manifest(start: Path) -> tuple[Path, Manifest]:
    """Find the project that holds a folder.

    Parameters
    ----------
    start : Path
        A folder inside the project, or the project itself.

    Returns
    -------
    tuple of (Path, Manifest)
        The project folder and its manifest.

    Raises
    ------
    FileNotFoundError
        If no folder from `start` up to the root has a `project.yaml`.
    """
    for folder in (start, *start.parents):
        if (folder / PROJECT_FILE).is_file():
            return folder, read_manifest(folder / PROJECT_FILE)
    raise FileNotFoundError(
        f"no {PROJECT_FILE} from {start} upwards; create the project "
        "with `riscv-tools new-project`"
    )
