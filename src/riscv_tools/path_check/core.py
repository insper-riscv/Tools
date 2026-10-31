r"""Verify that the file paths a project configuration names exist.

A manifest (YAML) lists the references to check:

```yaml
references:
  - name: sim sources
    file: Tests/tools/riscv_build/config.yaml
    yaml: sim.vhdl_sources    # dotted path; `*` walks a mapping or list
    base: Tests               # what the paths are relative to
  - name: quartus project
    file: tests/FPGA/core/quartus/core_fpga_test.qsf
    pattern: 'VHDL_FILE (\S+)'  # group 1 of every match
  - name: directories
    paths: [src, tests/FPGA]  # literal paths
```

`file` and `base` are relative to the root; `base` may be `@file` (the
directory of the referencing file, the default). A value with an
environment variable (`$QUARTUS_ROOTDIR/...`) is skipped. A reference
that yields no path fails.
"""

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml


def _children(node: Any) -> list[Any]:
    """List the values a `*` wildcard walks over.

    Parameters
    ----------
    node : Any
        A parsed YAML node.

    Returns
    -------
    list of Any
        A mapping's values, a list itself, or nothing for a scalar.
    """
    if isinstance(node, dict):
        return list(cast("dict[str, Any]", node).values())
    if isinstance(node, list):
        return cast("list[Any]", node)
    return []


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
        return [leaf for c in _children(node) for leaf in _walk(c, rest)]
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


def _base_of(reference: dict[str, Any], file: Path, root: Path) -> Path:
    """Return the directory a reference's paths are relative to.

    Parameters
    ----------
    reference : dict of {str: Any}
        A manifest entry, optionally with `base`.
    file : Path
        The referencing file.
    root : Path
        The root that `base` is relative to.

    Returns
    -------
    Path
        The file's directory for `@file` (the default), else the base
        under the root.
    """
    base = reference.get("base", "@file")
    return file.parent if base == "@file" else root / base


def _found_in(reference: dict[str, Any], file: Path) -> list[str]:
    """Read the raw path strings a `yaml` or `pattern` entry yields.

    Parameters
    ----------
    reference : dict of {str: Any}
        A manifest entry with `yaml` or `pattern`.
    file : Path
        The file to read.

    Returns
    -------
    list of str
        The path strings found.

    Raises
    ------
    ValueError
        If the entry has neither `yaml` nor `pattern`.
    """
    if "yaml" in reference:
        data = yaml.safe_load(file.read_text())
        return _strings(_walk(data, str(reference["yaml"]).split(".")))
    if "pattern" in reference:
        pattern: re.Pattern[str] = re.compile(
            str(reference["pattern"]), re.MULTILINE
        )
        return [str(m.group(1)) for m in pattern.finditer(file.read_text())]
    raise ValueError("reference needs `paths`, `yaml` or `pattern`")


def collect(reference: dict[str, Any], root: Path) -> list[Path]:
    """Resolve the paths one reference names.

    Parameters
    ----------
    reference : dict of {str: Any}
        A manifest entry: `paths`, or `file` with `yaml` or `pattern`,
        and optionally `base`.
    root : Path
        The root that `file`, `base` and `paths` are relative to.

    Returns
    -------
    list of Path
        The absolute path of each reference; empty when the reference
        yields none. Values holding `$VARIABLE` are left out.

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
    base = _base_of(reference, file, root)
    found = _found_in(reference, file)
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
        How many paths were checked, and one message per problem (a
        missing path, an unreadable file, a reference that yields
        nothing).
    """
    data = cast("dict[str, Any]", yaml.safe_load(manifest.read_text()) or {})
    references = cast("list[dict[str, Any]]", data.get("references") or [])
    checked = 0
    problems: list[str] = []
    for reference in references:
        found, issues = _check_reference(reference, root)
        checked += found
        problems += issues
    return checked, problems


def _check_reference(
    reference: dict[str, Any], root: Path
) -> tuple[int, list[str]]:
    """Check the paths of one manifest reference.

    Parameters
    ----------
    reference : dict of {str: Any}
        A manifest entry.
    root : Path
        The root the entry's files and bases are relative to.

    Returns
    -------
    tuple of (int, list of str)
        How many paths were checked, and one message per problem.
    """
    name = str(reference.get("name") or reference.get("file") or "paths")
    try:
        paths = collect(reference, root)
    except (ValueError, OSError, yaml.YAMLError, re.error) as exc:
        return 0, [f"{name}: {exc}"]
    problems: list[str] = []
    if not paths and not reference.get("optional"):
        problems.append(
            f"{name}: no path found (the list moved or was reformatted)"
        )
    for path in paths:
        if not path.exists():
            shown = Path(os.path.normpath(path)).relative_to(
                root, walk_up=True
            )
            problems.append(f"{name}: missing {shown}")
    return len(paths), problems
