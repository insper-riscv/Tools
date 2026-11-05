"""Resolve the files of a target from the `provides` manifests.

The target is a component. Its dependencies come first, depth first and
in the order the manifest lists them, then its own files in their listed
order, and no file appears twice. The manifests searched are the one of
the root itself and the ones of the repositories mounted below it (the
submodules of `.gitmodules`, and `src/common`).
"""

import configparser
import os
from pathlib import Path

from riscv_tools.tree_check.manifest import Provides, load_provides


class SourcesError(ValueError):
    """A target or dependency that no manifest declares."""


def _mounts(root: Path) -> list[Path]:
    """List the folders below the root that may hold a repository.

    Parameters
    ----------
    root : Path
        The workspace root.

    Returns
    -------
    list of Path
        The submodule paths of `.gitmodules`, then `src/common`.
    """
    found: list[Path] = []
    gitmodules = root / ".gitmodules"
    if gitmodules.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(gitmodules.read_text())
        found.extend(
            root / parser.get(section, "path")
            for section in parser.sections()
            if parser.has_option(section, "path")
        )
    found.append(root / "src" / "common")
    return found


def workspace(root: Path) -> dict[str, tuple[Path, Provides]]:
    """Load the manifests of the root and of the repositories below it.

    Parameters
    ----------
    root : Path
        The workspace root.

    Returns
    -------
    dict of str to tuple of (Path, Provides)
        The folder and the manifest of each repository, keyed by the
        repository name; the root comes first, and a repository seen
        twice keeps its first folder.

    Raises
    ------
    SourcesError
        If a manifest is malformed.
    """
    found: dict[str, tuple[Path, Provides]] = {}
    for folder in (root, *_mounts(root)):
        mount = folder.relative_to(root).as_posix() == "src/common"
        provides, problems = load_provides(
            folder, "Common-Components" if mount else None
        )
        if problems:
            raise SourcesError(
                f"{folder}: invalid provides: {'; '.join(problems)}"
            )
        if provides is not None:
            found.setdefault(provides.repository, (folder, provides))
    return found


def _split(name: str, current: str) -> tuple[str, str]:
    """Split `<repository>/<component>`, defaulting to the current one.

    Parameters
    ----------
    name : str
        The component as written.
    current : str
        The repository the name was written in.

    Returns
    -------
    tuple of (str, str)
        The repository and the component.
    """
    repository, _, component = name.rpartition("/")
    return (repository or current), component


def ordered_sources(root: Path, targets: list[str]) -> list[str]:
    """List the files of the targets, dependencies first.

    Parameters
    ----------
    root : Path
        The workspace root; the paths returned are relative to it.
    targets : list of str
        Components as `<repository>/<component>`; a bare name means the
        repository of the root.

    Returns
    -------
    list of str
        The files in analysis order, without repeats, in POSIX form.

    Raises
    ------
    SourcesError
        If a repository or component is not found or a cycle is met.
    """
    repositories = workspace(root)
    if not repositories:
        raise SourcesError(f"no provides manifest found under {root}")
    own = next(iter(repositories))
    result: list[str] = []
    done: set[tuple[str, str]] = set()
    active: list[tuple[str, str]] = []

    def visit(repository: str, component: str) -> None:
        key = (repository, component)
        if key in done:
            return
        if key in active:
            raise SourcesError(f"cycle at {repository}/{component}")
        if repository not in repositories:
            raise SourcesError(f"repository {repository} not found")
        folder, provides = repositories[repository]
        if component not in provides.components:
            raise SourcesError(f"{repository}/{component} not declared")
        active.append(key)
        item = provides.components[component]
        for dep in item.requires:
            visit(*_split(dep, repository))
        active.pop()
        done.add(key)
        for path in item.sources:
            relative = Path(os.path.relpath(folder / path, root)).as_posix()
            if relative not in result:
                result.append(relative)

    for target in targets:
        visit(*_split(target, own))
    return result
