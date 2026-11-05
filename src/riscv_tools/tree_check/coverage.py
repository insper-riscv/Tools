"""Check that each entity of `src/` has its test and, if due, its proof.

The coverage rule of the target tree (section 4.2 of the reorganization
plan): each entity of the RTL has an entry in `tests/python/tests.json`
whose top level is that entity (or its testbench, `<name>_tb`) and
whose sources include its file, and each entity named in the table of
proofs has its proof in `formal/`: `<name>.sv`, `<name>_props.sv` or
`<name>/props.sv`, or the files the table names for it.

The repository's `paths.yaml` carries the data in a `coverage` section
of `tree`:

```yaml
tree:
  coverage:
    formal:
      sdram_arbiter: []
      axi_master_bridge: [formal/axi_master/props.sv]
    exceptions:
      boot_rom_shell: wraps a Quartus IP, covered by the synthesis
```

An exception excuses the test only, never the proof, and is never
accepted without its justification.
"""

import json
import re
from pathlib import Path
from typing import Any, cast

from riscv_tools.repo_walk import list_files
from riscv_tools.vhdl_style import is_generated_ip

_ENTITY = re.compile(
    r"^\s*entity\s+(\w+)\s+is\b", re.IGNORECASE | re.MULTILINE
)
_MODEL_FOLDERS = frozenset({"sim", "tests"})
_TESTS = Path("tests/python/tests.json")


def _strip(text: str) -> str:
    """Remove the line comments of VHDL text.

    Parameters
    ----------
    text : str
        The content of a file.

    Returns
    -------
    str
        The text without comments.
    """
    return re.sub(r"--[^\n]*", "", text)


def rtl_entities(root: Path) -> dict[str, str]:
    """Find the entities of the RTL under `src/`.

    Simulation models and wrappers (folders `sim` and `tests`), third
    party code and Quartus IPs are not RTL and are left out.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    dict of str to str
        The file of each entity, relative to the root, keyed by the
        entity name in lowercase.
    """
    found: dict[str, str] = {}
    for path in list_files(root / "src", ".vhd"):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if _MODEL_FOLDERS & set(relative.split("/")[:-1]):
            continue
        if is_generated_ip(relative, text):
            continue
        for match in _ENTITY.finditer(_strip(text)):
            found[match.group(1).lower()] = relative
    return found


def _test_entries(root: Path) -> list[dict[str, Any]]:
    """Read the entries of `tests/python/tests.json`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of dict of str to Any
        The entries; empty when the file is absent, empty or malformed
        (`check-paths` and the test run report a broken file).
    """
    manifest = root / _TESTS
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return [
        cast("dict[str, Any]", entry)
        for entry in cast("dict[str, Any]", data).values()
        if isinstance(entry, dict)
    ]


def _tested(entries: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Index the top levels of the tests with their sources.

    Parameters
    ----------
    entries : list of dict of str to Any
        The entries of `tests.json`.

    Returns
    -------
    dict of str to set of str
        For each top level in lowercase, the sources of the tests that
        have it. A testbench named after its entity (`<name>_tb`) counts
        as that entity.
    """
    index: dict[str, set[str]] = {}
    for entry in entries:
        top = str(entry.get("toplevel", "")).lower().removesuffix("_tb")
        sources = entry.get("sources", [])
        listed = (
            cast("list[Any]", sources) if isinstance(sources, list) else []
        )
        index.setdefault(top, set()).update(str(item) for item in listed)
    return index


def _section(config: dict[str, Any]) -> dict[str, Any]:
    """Read the `coverage` section of the `tree` configuration.

    Parameters
    ----------
    config : dict of str to Any
        The `tree` section of `paths.yaml`.

    Returns
    -------
    dict of str to Any
        The section, empty when absent.
    """
    section = config.get("coverage")
    if not isinstance(section, dict):
        return {}
    return cast("dict[str, Any]", section)


def _exceptions(section: dict[str, Any]) -> dict[str, str]:
    """Read the entities that are excused, with their justification.

    Parameters
    ----------
    section : dict of str to Any
        The `coverage` section.

    Returns
    -------
    dict of str to str
        The justification of each excused entity, keyed by lowercase
        name.
    """
    listed = section.get("exceptions", {})
    if not isinstance(listed, dict):
        return {}
    return {
        str(name).lower(): str(why or "").strip()
        for name, why in cast("dict[Any, Any]", listed).items()
    }


def _formal(section: dict[str, Any]) -> dict[str, list[str]]:
    """Read the entities that must have a proof.

    Parameters
    ----------
    section : dict of str to Any
        The `coverage` section: a list of entity names, or a mapping
        from the name to the proof files when they do not follow the
        naming of `_candidates`.

    Returns
    -------
    dict of str to list of str
        The proof files named for each entity (empty for the default
        names), keyed by lowercase entity name.
    """
    listed = section.get("formal", [])
    if isinstance(listed, list):
        return {str(name).lower(): [] for name in cast("list[Any]", listed)}
    if not isinstance(listed, dict):
        return {}
    found: dict[str, list[str]] = {}
    for name, files in cast("dict[Any, Any]", listed).items():
        named = [files] if isinstance(files, str) else files
        found[str(name).lower()] = (
            [str(item) for item in cast("list[Any]", named)]
            if isinstance(named, list)
            else []
        )
    return found


def _candidates(name: str) -> list[str]:
    """List the default places of the proof of an entity.

    Parameters
    ----------
    name : str
        The entity name in lowercase.

    Returns
    -------
    list of str
        The paths relative to the root.
    """
    return [
        f"formal/{name}.sv",
        f"formal/{name}_props.sv",
        f"formal/{name}/props.sv",
    ]


def _formal_problems(
    root: Path,
    proofs: dict[str, list[str]],
    entities: dict[str, str],
) -> list[str]:
    """Report the proofs that are missing.

    Parameters
    ----------
    root : Path
        The repository root.
    proofs : dict of str to list of str
        The table of proofs.
    entities : dict of str to str
        The RTL entities.

    Returns
    -------
    list of str
        One problem for each proof that names no entity or has no file.
    """
    problems: list[str] = []
    for name, files in proofs.items():
        if name not in entities:
            problems.append(f"formal {name} names no entity of src/")
        elif files:
            problems.extend(
                f"missing {path}, the proof of {name}"
                for path in files
                if not (root / path).is_file()
            )
        elif not any((root / path).is_file() for path in _candidates(name)):
            problems.append(
                f"missing {' or '.join(_candidates(name))}, "
                f"the proof of {name}"
            )
    return problems


def _test_problems(
    entities: dict[str, str], tested: dict[str, set[str]], skip: set[str]
) -> list[str]:
    """Report the entities without a test of their own.

    Parameters
    ----------
    entities : dict of str to str
        The RTL entities and their files.
    tested : dict of str to set of str
        The top levels of `tests.json` and their sources.
    skip : set of str
        The excused entities.

    Returns
    -------
    list of str
        One problem for each entity not covered.
    """
    problems: list[str] = []
    for name, file in sorted(entities.items()):
        if name in skip:
            continue
        if name not in tested:
            problems.append(
                f"{name} ({file}) has no entry in {_TESTS} with it as toplevel"
            )
        elif file not in tested[name]:
            problems.append(
                f"{name}: the test in {_TESTS} does not list {file} "
                "in its sources"
            )
    return problems


def rule_entity_coverage(
    root: Path, _kind: str, config: dict[str, Any]
) -> list[str]:
    """Report entities without a test and proofs that are missing.

    Parameters
    ----------
    root : Path
        The repository root.
    _kind : str
        The kind of repository; unused by this rule.
    config : dict of str to Any
        The `tree` section, with the optional `coverage`.

    Returns
    -------
    list of str
        One problem for each entity without a test, each named proof
        without its file, each excuse without justification and each
        excuse or proof for an entity that does not exist.
    """
    section = _section(config)
    entities = rtl_entities(root)
    excused = _exceptions(section)
    problems = _test_problems(
        entities, _tested(_test_entries(root)), set(excused)
    )
    problems.extend(
        f"exception {name} has no justification"
        for name, why in sorted(excused.items())
        if not why
    )
    problems.extend(
        f"exception {name} names no entity of src/"
        for name in sorted(excused)
        if name not in entities
    )
    problems.extend(_formal_problems(root, _formal(section), entities))
    return problems
