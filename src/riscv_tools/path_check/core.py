r"""Verify that the file paths a project's configuration references exist.

Moving a VHDL file between repositories breaks every list that names it: the
simulation's source list, the tests' `tests.json`, the Quartus project's
`VHDL_FILE` lines. Each breaks only when something runs it. This module reads
those lists and fails when a listed path does not exist, so a move is checked
before anything is built.

A manifest (YAML) lists the references to check:

```yaml
references:
  - name: sim sources
    file: Tests/tools/riscv_build/config.yaml   # relative to the root
    yaml: sim.vhdl_sources                      # dotted path; `*` walks a
                                                # mapping's values or a list
    base: Tests                                 # what the paths are relative
                                                # to (default: the file's dir)
  - name: quartus project
    file: tests/FPGA/core/quartus/core_fpga_test.qsf
    pattern: 'VHDL_FILE (\S+)'                  # group 1 of every match
  - name: directories
    paths: [src, tests/FPGA]                    # literal, relative to the root
```

`base` and `file` are relative to the root; `base` may be `@file` (the
referencing file's directory, the default). A value that holds an environment
variable (`$QUARTUS_ROOTDIR/...`) is skipped: it depends on the machine. A
reference that yields no path at all fails, so a list that was renamed or
reformatted out of reach is noticed.
"""

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml


def _walk(node: Any, keys: list[str]) -> list[Any]:
    """Follow a dotted path through parsed YAML, with `*` as a wildcard.

    Parameters
    ----------
    node : Any
        The parsed document or a part of it.
    keys : list of str
        The remaining path components.

    Returns
    -------
    list of Any
        Every value the path reaches; empty when it does not exist.
    """
    if not keys:
        return [node]
    key, rest = keys[0], keys[1:]
    if key == "*":
        children: list[Any] = []
        if isinstance(node, dict):
            children = list(cast("dict[str, Any]", node).values())
        elif isinstance(node, list):
            children = cast("list[Any]", node)
        return [leaf for child in children for leaf in _walk(child, rest)]
    if isinstance(node, dict) and key in node:
        return _walk(cast("dict[str, Any]", node)[key], rest)
    return []


def _strings(values: list[Any]) -> list[str]:
    """Flatten values that are strings or lists of strings.

    Parameters
    ----------
    values : list of Any
        Values reached in a document.

    Returns
    -------
    list of str
        The strings among them, lists expanded; anything else dropped.
    """
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out += [v for v in cast("list[Any]", value) if isinstance(v, str)]
    return out


def collect(reference: dict[str, Any], root: Path) -> list[Path]:
    """Resolve the paths one reference names.

    Parameters
    ----------
    reference : dict of {str: Any}
        A manifest entry: `paths`, or `file` with `yaml` or `pattern`, and
        optionally `base`.
    root : Path
        The root that `file`, `base` and `paths` are relative to.

    Returns
    -------
    list of Path
        The absolute path of each reference; empty when the reference yields
        none. Values holding `$VARIABLE` are left out.

    Raises
    ------
    ValueError
        If the entry has none of `paths`, `yaml` or `pattern`.
    OSError
        If `file` cannot be read.
    """
    if "paths" in reference:
        return [root / p for p in reference["paths"]]
    file = root / reference["file"]
    base = (
        file.parent
        if reference.get("base", "@file") == "@file"
        else root / reference["base"]
    )
    found: list[str]
    if "yaml" in reference:
        data = yaml.safe_load(file.read_text())
        found = _strings(_walk(data, str(reference["yaml"]).split(".")))
    elif "pattern" in reference:
        pattern: re.Pattern[str] = re.compile(str(reference["pattern"]), re.MULTILINE)
        found = [str(m.group(1)) for m in pattern.finditer(file.read_text())]
    else:
        raise ValueError("reference needs `paths`, `yaml` or `pattern`")
    return [base / p for p in found if "$" not in p]


def check_paths(manifest: Path, root: Path) -> tuple[int, list[str]]:
    """Check that every path a manifest's references name exists.

    Parameters
    ----------
    manifest : Path
        The manifest YAML.
    root : Path
        The root the manifest's files and bases are relative to.

    Returns
    -------
    tuple of (int, list of str)
        How many paths were checked, and one message per problem (a missing
        path, an unreadable file, a reference that yields nothing).
    """
    data = cast("dict[str, Any]", yaml.safe_load(manifest.read_text()) or {})
    references = cast("list[dict[str, Any]]", data.get("references") or [])
    checked = 0
    problems: list[str] = []
    for reference in references:
        name = str(reference.get("name") or reference.get("file") or "paths")
        try:
            paths = collect(reference, root)
        except (ValueError, OSError, yaml.YAMLError, re.error) as exc:
            problems.append(f"{name}: {exc}")
            continue
        if not paths and not reference.get("optional"):
            problems.append(
                f"{name}: no path found (the list moved or was reformatted)"
            )
        for path in paths:
            checked += 1
            if not path.exists():
                shown = Path(os.path.normpath(path)).relative_to(root, walk_up=True)
                problems.append(f"{name}: missing {shown}")
    return checked, problems
