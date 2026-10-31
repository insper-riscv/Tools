"""Sort VHDL sources into GHDL-analyzable dependency order.

GHDL analyzes a design unit only after the entities it instantiates and
the packages it uses, so the order matters. The order is derived from
the files' own content with lightweight regex parsing, without invoking
GHDL.
"""

import re
from pathlib import Path

ENTITY_DECL_RE = re.compile(r"\bentity\s+(\w+)\s+is\b", re.IGNORECASE)
PACKAGE_DECL_RE = re.compile(r"\bpackage\s+(\w+)\s+is\b", re.IGNORECASE)
ENTITY_DEP_RE = re.compile(r"\bentity\s+work\.(\w+)", re.IGNORECASE)
USE_DEP_RE = re.compile(r"\buse\s+work\.(\w+)", re.IGNORECASE)


def _scan_file(
    f: Path,
    text: str,
    unit_file: dict[str, Path],
    file_deps: dict[Path, set[str]],
) -> None:
    """Record the design units a file declares and the ones it uses.

    Parameters
    ----------
    f : Path
        The file the text was read from.
    text : str
        The file's content.
    unit_file : dict of {str: Path}
        Maps a design unit name to its declaring file; updated in
        place.
    file_deps : dict of {Path: set of str}
        Maps a file to the names of the units it depends on; updated
        in place.
    """
    for m in ENTITY_DECL_RE.finditer(text):
        unit_file[m.group(1).lower()] = f

    for m in PACKAGE_DECL_RE.finditer(text):
        name = m.group(1).lower()
        if name != "body":
            unit_file[name] = f

    deps = file_deps.setdefault(f, set())
    deps.update(m.group(1).lower() for m in ENTITY_DEP_RE.finditer(text))
    deps.update(m.group(1).lower() for m in USE_DEP_RE.finditer(text))


def _dependency_order(
    files: list[Path],
    unit_file: dict[str, Path],
    file_deps: dict[Path, set[str]],
) -> list[Path]:
    """Depth-first order of files, dependencies first.

    Parameters
    ----------
    files : list of Path
        The files to order; traversal starts from them sorted.
    unit_file : dict of {str: Path}
        Maps a design unit name to its declaring file.
    file_deps : dict of {Path: set of str}
        Maps a file to the names of the units it depends on.

    Returns
    -------
    list of Path
        `files`, each one after the files it depends on; a cycle is
        broken arbitrarily.
    """
    file_set = set(files)
    visited: set[Path] = set()
    visiting: set[Path] = set()
    result: list[Path] = []

    def visit(f: Path) -> None:
        if f in visited or f in visiting:
            return
        visiting.add(f)
        for dep_name in file_deps.get(f, set()):
            dep_file = unit_file.get(dep_name)
            if dep_file is not None and dep_file != f and dep_file in file_set:
                visit(dep_file)
        visiting.discard(f)
        visited.add(f)
        result.append(f)

    for f in sorted(files):
        visit(f)

    return result


def topo_sort(files: list[Path]) -> list[Path]:
    """Sort VHDL files so each one's `work.*` dependencies precede it.

    Parameters
    ----------
    files : list of Path
        VHDL source files to order. A dependency whose declaring file
        isn't in `files` is ignored, and an unreadable file is skipped
        but still appears in the output.

    Returns
    -------
    list of Path
        `files`, reordered so each file's `work.*` dependencies (per
        this module's regex parsing of entity/package declarations
        and references) appear before it. Traversal starts from
        `files` sorted alphabetically, so the result is deterministic
        across runs for the same input set. A dependency cycle is
        broken arbitrarily rather than raising; GHDL itself will
        reject a genuine circular dependency at analyze time with a
        clearer error than this module could produce.
    """
    unit_file: dict[str, Path] = {}
    file_deps: dict[Path, set[str]] = {}

    for f in files:
        try:
            text = f.read_text()
        except OSError, UnicodeDecodeError:
            continue
        _scan_file(f, text, unit_file, file_deps)

    return _dependency_order(files, unit_file, file_deps)
