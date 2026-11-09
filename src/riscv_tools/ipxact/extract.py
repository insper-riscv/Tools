"""Extract the entities of a repository from its VHDL.

The files are analyzed in the order the `provides` manifests give, the
ones of the repository and those of the repositories mounted below it,
then the syntax tree of each component is read for its entities.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from riscv_tools.ipxact import ghdl_ast, stub
from riscv_tools.ipxact.model import Entity, ExtractError
from riscv_tools.sources import ordered_sources
from riscv_tools.sources.core import workspace


@dataclass(frozen=True)
class Found:
    """An entity and the component of the manifest that lists its file.

    Parameters
    ----------
    entity : Entity
        The entity read from the VHDL.
    component : str
        The name of the component in `provides`.
    sources : tuple of str
        The files of that component, relative to the repository root.
    """

    entity: Entity
    component: str
    sources: tuple[str, ...]


def _prepare(root: Path, paths: list[str], scratch: Path) -> dict[Path, Path]:
    """Choose the file to analyze for each source.

    Parameters
    ----------
    root : Path
        The workspace root.
    paths : list of str
        The sources, dependencies first, relative to the root.
    scratch : Path
        Where the reduced files go.

    Returns
    -------
    dict of Path to Path
        The analyzed path of each source, in order, to the original.
    """
    chosen: dict[Path, Path] = {}
    for position, name in enumerate(paths):
        original = (root / name).resolve()
        if stub.needs_vendor_library(original.read_text()):
            reduced = scratch / "stubs" / str(position) / original.name
            stub.write_stub(original, reduced)
            chosen[reduced] = original
        else:
            chosen[original] = original
    return chosen


def _component(
    root: Path, own: str, name: str, sources: tuple[str, ...]
) -> tuple[list[Found], dict[str, str]]:
    """Read the entities of one component, analyzing its closure.

    Parameters
    ----------
    root : Path
        The workspace root.
    own : str
        The name of the repository.
    name : str
        The component name.
    sources : tuple of str
        The files of the component.

    Returns
    -------
    tuple of (list of Found, dict of str to str)
        The entities of the component and, for each one that could not
        be translated, the reason.
    """
    order = ordered_sources(root, [f"{own}/{name}"])
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        chosen = _prepare(root, order, work)
        ghdl_ast.analyze(list(chosen), work)
        by_original = {original: path for path, original in chosen.items()}
        wanted = {
            by_original[(root / path).resolve()]: (root / path).resolve()
            for path in sources
        }
        tree = ghdl_ast.dump(list(chosen), work)
        read = ghdl_ast.entities(tree, root, wanted)
        return [Found(entity, name, sources) for entity in read.entities], (
            read.failures
        )


class Extraction(NamedTuple):
    """The result of reading a repository.

    Parameters
    ----------
    found : list of Found
        The entities read.
    failures : dict of str to str
        For each entity, or component when GHDL rejects it, that could
        not be read, the reason.
    """

    found: list[Found]
    failures: dict[str, str]


def extract(root: Path) -> Extraction:
    """Read every entity the manifest of a repository lists.

    Each component is analyzed with its own closure in a library of its
    own, because a repository may list two components that declare the
    same entity (a simulation model next to the real block).

    Parameters
    ----------
    root : Path
        The repository root (a workspace whose first manifest is the
        repository's own).

    Returns
    -------
    Extraction
        The entities with their component, in manifest order, and the
        components that failed.

    Raises
    ------
    ExtractError
        If the repository has no manifest.
    """
    root = root.resolve()
    repositories = workspace(root)
    if not repositories:
        raise ExtractError(f"no provides manifest under {root}")
    own, (_, provides) = next(iter(repositories.items()))
    found: list[Found] = []
    failures: dict[str, str] = {}
    for name, component in provides.components.items():
        try:
            read, bad = _component(root, own, name, component.sources)
        except ExtractError as error:
            failures[name] = str(error)
            continue
        found.extend(read)
        failures.update(bad)
    return Extraction(found, failures)
