"""Generate and check the IP-XACT documents of a repository."""

import difflib
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.ipxact import manifest
from riscv_tools.ipxact.component import Source, build, serialize
from riscv_tools.ipxact.extract import Extraction, extract
from riscv_tools.ipxact.model import ExtractError
from riscv_tools.ipxact.schema import schema_errors
from riscv_tools.ipxact.semantic import check_component
from riscv_tools.ipxact.vlnv import (
    VENDOR,
    Vlnv,
    library_of,
    repository_version,
)
from riscv_tools.sources.core import workspace

OUTPUT = "ipxact"
SUFFIX = ".component.xml"


@dataclass(frozen=True)
class Plan:
    """The documents a repository should have.

    Parameters
    ----------
    documents : dict of str to str
        The text of each document, keyed by file name.
    problems : list of str
        What stops a document from being generated.
    """

    documents: dict[str, str]
    problems: list[str]


def _exception_problems(
    extraction: Extraction, skipped: dict[str, str], components: set[str]
) -> list[str]:
    """List the exceptions that are not needed or match nothing.

    Parameters
    ----------
    extraction : Extraction
        What was read from the VHDL.
    skipped : dict of str to str
        The exceptions of `paths.yaml`.
    components : set of str
        The components of the manifest.

    Returns
    -------
    list of str
        An exception on an entity that translates, an exception that
        names nothing, and each failure no exception covers.
    """
    entities = {item.entity.name for item in extraction.found}
    problems: list[str] = []
    for name in sorted(skipped):
        if name in entities:
            problems.append(
                f"exception {name}: the entity translates, remove it"
            )
        elif name not in extraction.failures and name not in components:
            problems.append(f"exception {name}: names no entity or component")
    problems.extend(
        f"{name}: {reason}"
        for name, reason in extraction.failures.items()
        if name not in skipped
    )
    return problems


def plan(root: Path) -> Plan:
    """Work out the documents of a repository from its VHDL.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    Plan
        The documents and the problems that stop others.
    """
    root = root.resolve()
    extraction = extract(root)
    skipped, problems = manifest.exceptions(root)
    repositories = workspace(root)
    own = next(iter(repositories))
    provides = repositories[own][1]
    version = repository_version(root)
    documents: dict[str, str] = {}
    for item in extraction.found:
        entity = item.entity
        if entity.name in skipped or item.component in skipped:
            continue
        vlnv = Vlnv(VENDOR, library_of(own), entity.name, version)
        name = vlnv.file_name("component")
        if name in documents:
            problems.append(f"{entity.name}: declared by two components")
            continue
        requires = provides.components[item.component].requires
        source = Source(vlnv, item.component, item.sources, requires)
        documents[name] = serialize(build(entity, source))
    problems.extend(
        _exception_problems(extraction, skipped, set(provides.components))
    )
    return Plan(documents, problems)


def _stored(root: Path) -> dict[str, str]:
    """Read the component documents the repository has."""
    folder = root / OUTPUT
    if not folder.is_dir():
        return {}
    return {
        path.name: path.read_text()
        for path in sorted(folder.glob(f"*{SUFFIX}"))
    }


def differences(root: Path, documents: dict[str, str]) -> list[str]:
    """Compare the stored documents with the generated ones.

    Parameters
    ----------
    root : Path
        The repository root.
    documents : dict of str to str
        The generated documents.

    Returns
    -------
    list of str
        One line for each missing, stale or different document.
    """
    stored = _stored(root)
    found = [
        f"{OUTPUT}/{name}: missing, run `riscv-tools ipxact generate`"
        for name in sorted(documents.keys() - stored.keys())
    ]
    found.extend(
        f"{OUTPUT}/{name}: stale, not generated from any entity"
        for name in sorted(stored.keys() - documents.keys())
    )
    for name in sorted(documents.keys() & stored.keys()):
        if documents[name] != stored[name]:
            delta = difflib.unified_diff(
                stored[name].splitlines(),
                documents[name].splitlines(),
                lineterm="",
                n=0,
            )
            first = next((x for x in list(delta)[2:] if x[0] in "+-"), "")
            found.append(f"{OUTPUT}/{name}: differs from the VHDL ({first})")
    return found


def write(root: Path, documents: dict[str, str]) -> list[str]:
    """Write the documents and remove the stale ones.

    Parameters
    ----------
    root : Path
        The repository root.
    documents : dict of str to str
        The generated documents.

    Returns
    -------
    list of str
        The names written.
    """
    folder = root / OUTPUT
    folder.mkdir(exist_ok=True)
    for name in sorted(_stored(root).keys() - documents.keys()):
        (folder / name).unlink()
    for name, text in documents.items():
        (folder / name).write_text(text)
    return sorted(documents)


def validate(root: Path) -> list[str]:
    """Validate the stored documents against the standard.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of str
        The schema violations and the broken semantic rules.
    """
    found: list[str] = []
    for path in sorted((root / OUTPUT).glob(f"*{SUFFIX}")):
        errors = schema_errors(path)
        found.extend(errors)
        if not errors:
            found.extend(check_component(path))
    return found


def check(root: Path) -> list[str]:
    """Run every check of the repository.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of str
        The problems: what cannot be generated, what differs from the
        stored documents and what the standard rejects in them.
    """
    try:
        planned = plan(root)
    except ExtractError as error:
        return [str(error)]
    return [
        *planned.problems,
        *differences(root, planned.documents),
        *validate(root),
    ]
