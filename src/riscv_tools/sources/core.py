"""Resolve the files of a target from the `provides` manifests.

The target is a component. Its dependencies come first, depth first and
in the order the manifest lists them, then its own files in their listed
order, and no file appears twice. The manifests searched are the one of
the root itself and the ones of the repositories mounted below it (the
submodules of `.gitmodules`, and `src/common`).

A unit that a platform generates in place of a default one has the same
file name in both: the `config_pkg.vhd` of the Common-Components (the
default package of constants) and the one the platform generates. The
list keeps one file for each such name, the generated one, in the place
where the default would have been analyzed, so every unit that uses the
package still comes after it.
"""

import os
import posixpath
from pathlib import Path

from riscv_tools.repo_walk import submodule_paths
from riscv_tools.tree_check.manifest import (
    Component,
    Provides,
    load_provides,
)

# Os arquivos que a plataforma gera no lugar do padrão do repositório de
# componentes comuns, e o repositório que traz o padrão.
SWAPPABLE = frozenset({"config_pkg.vhd"})
DEFAULT_REPOSITORY = "Common-Components"


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
    found = [root / path for path in sorted(submodule_paths(root))]
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


def _lookup(
    repositories: dict[str, tuple[Path, Provides]],
    repository: str,
    component: str,
) -> tuple[Path, Component]:
    """Find a component in the loaded repositories.

    Parameters
    ----------
    repositories : dict of str to tuple of (Path, Provides)
        The folder and the manifest of each repository.
    repository : str
        The repository the component is expected in.
    component : str
        The component name.

    Returns
    -------
    tuple of (Path, Component)
        The folder of the repository and the component.

    Raises
    ------
    SourcesError
        If the repository is not loaded or does not declare the
        component.
    """
    if repository not in repositories:
        raise SourcesError(f"repository {repository} not found")
    folder, provides = repositories[repository]
    if component not in provides.components:
        raise SourcesError(f"{repository}/{component} not declared")
    return folder, provides.components[component]


class _Walk:
    """The depth-first walk over the components of the manifests."""

    def __init__(
        self, repositories: dict[str, tuple[Path, Provides]], root: Path
    ) -> None:
        """Start a walk with nothing visited.

        Parameters
        ----------
        repositories : dict of str to tuple of (Path, Provides)
            The folder and the manifest of each repository.
        root : Path
            The workspace root, which the paths are relative to.
        """
        self.repositories = repositories
        self.root = root
        self.result: list[str] = []
        self.needs: set[str] = set()
        self.done: set[tuple[str, str]] = set()
        self.active: list[tuple[str, str]] = []
        self.slots: dict[str, tuple[int, str]] = {}

    def _add(self, path: str, repository: str) -> None:
        """Add a file, unless it is listed already.

        A file of `SWAPPABLE` shares one slot with the others of its
        name: a file of another repository than the default one takes
        the slot of the default, and the default never takes the slot of
        another.

        Parameters
        ----------
        path : str
            The path relative to the workspace root, in POSIX form.
        repository : str
            The repository of the component that lists the file.
        """
        name = posixpath.basename(path)
        if name not in SWAPPABLE:
            if path not in self.result:
                self.result.append(path)
            return
        if name not in self.slots:
            self.slots[name] = (len(self.result), repository)
            self.result.append(path)
        elif repository != DEFAULT_REPOSITORY:
            index = self.slots[name][0]
            self.result[index] = path
            self.slots[name] = (index, repository)

    def visit(self, repository: str, component: str) -> None:
        """Add a component after its dependencies.

        Parameters
        ----------
        repository : str
            The repository of the component.
        component : str
            The component name.

        Raises
        ------
        SourcesError
            If the component is missing or part of a cycle.
        """
        key = (repository, component)
        if key in self.done:
            return
        if key in self.active:
            raise SourcesError(f"cycle at {repository}/{component}")
        folder, item = _lookup(self.repositories, repository, component)
        self.active.append(key)
        for dep in item.requires:
            self.visit(*_split(dep, repository))
        self.active.pop()
        self.done.add(key)
        self.needs.update(item.needs)
        for path in item.sources:
            relative = Path(os.path.relpath(folder / path, self.root))
            self._add(relative.as_posix(), repository)


def _walked(root: Path, targets: list[str]) -> _Walk:
    """Walk the components of the targets, dependencies first.

    Parameters
    ----------
    root : Path
        The workspace root.
    targets : list of str
        Components as `<repository>/<component>`; a bare name means the
        repository of the root.

    Returns
    -------
    _Walk
        The finished walk, which holds the files and the board
        resource types of the closure.

    Raises
    ------
    SourcesError
        If a repository or component is not found or a cycle is met.
    """
    repositories = workspace(root)
    if not repositories:
        raise SourcesError(f"no provides manifest found under {root}")
    own = next(iter(repositories))
    walk = _Walk(repositories, root)
    for target in targets:
        walk.visit(*_split(target, own))
    return walk


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
    return _walked(root, targets).result


def closure_needs(root: Path, targets: list[str]) -> list[str]:
    """List the board resource types the closure of the targets needs.

    The same walk as `ordered_sources`, so the `needs` come from the
    components that would be analyzed, the targets and everything they
    require.

    Parameters
    ----------
    root : Path
        The workspace root.
    targets : list of str
        Components as `<repository>/<component>`; a bare name means the
        repository of the root.

    Returns
    -------
    list of str
        The union of the `needs` of every component, sorted.

    Raises
    ------
    SourcesError
        If a repository or component is not found or a cycle is met.
    """
    return sorted(_walked(root, targets).needs)
