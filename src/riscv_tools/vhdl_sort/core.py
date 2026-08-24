"""Sort VHDL sources into GHDL-analyzable dependency order.

GHDL's `-a` (analyze) phase needs a design unit's dependencies
(entities it instantiates, packages it `use`s) analyzed before the
unit itself — feeding files in the wrong order fails with "primary
unit ... not found". Hand-ordering a project's VHDL file list is
tedious and breaks silently the moment a new dependency is added, so
this derives the order from the files' own content instead, via
lightweight regex parsing (no GHDL invocation, no real VHDL parser).
"""

import re
from pathlib import Path

ENTITY_DECL_RE = re.compile(r"\bentity\s+(\w+)\s+is\b", re.IGNORECASE)
PACKAGE_DECL_RE = re.compile(r"\bpackage\s+(\w+)\s+is\b", re.IGNORECASE)
ENTITY_DEP_RE = re.compile(r"\bentity\s+work\.(\w+)", re.IGNORECASE)
USE_DEP_RE = re.compile(r"\buse\s+work\.(\w+)", re.IGNORECASE)


def topo_sort(files: list[Path]) -> list[Path]:
    """Sort VHDL files so each one's `work.*` dependencies precede it.

    Parameters
    ----------
    files : list of Path
        VHDL source files to order. A dependency on a design unit
        whose declaring file isn't in `files` is silently ignored
        (assumed already available some other way, e.g. a vendor IP
        core excluded from this analysis order on purpose). A file
        that can't be read (missing, permission error, bad encoding)
        is skipped rather than raising — it still appears in the
        output, just with no dependency information contributing to
        its position.

    Returns
    -------
    list of Path
        `files`, reordered so each file's `work.*` dependencies (per
        this module's regex parsing of entity/package declarations
        and references) appear before it. Traversal starts from
        `files` sorted alphabetically, so the result is deterministic
        across runs for the same input set. A dependency cycle is
        broken arbitrarily rather than raising — GHDL itself will
        reject a genuine circular dependency at analyze time with a
        clearer error than this module could produce.
    """
    unit_file: dict[str, Path] = {}
    file_deps: dict[Path, set[str]] = {}

    for f in files:
        try:
            text = f.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        for m in ENTITY_DECL_RE.finditer(text):
            unit_file[m.group(1).lower()] = f

        for m in PACKAGE_DECL_RE.finditer(text):
            name = m.group(1).lower()
            if name != "body":
                unit_file[name] = f

        deps = file_deps.setdefault(f, set())
        deps.update(m.group(1).lower() for m in ENTITY_DEP_RE.finditer(text))
        deps.update(m.group(1).lower() for m in USE_DEP_RE.finditer(text))

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
