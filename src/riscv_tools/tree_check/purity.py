"""Check that no board, family or vendor name leaks out of its folder.

The portable part of a repository (the SoC, the cores, the memories)
talks to its neighbours through interface contracts and does not name a
board, an FPGA family or a vendor primitive. Those names live in the
vendor folders (`altera/`) and in the board data (`boards/`). The
`purity` rule of `check-tree` reads the files of the walk (see
`repo_walk`) outside those folders and reports each term it finds.

The terms are data. `purity.yaml`, next to this module, carries the
defaults; the `purity` subsection of the `tree` section of the
repository's `paths.yaml` adds to them:

```yaml
tree:
  purity:
    vendor_folders: [cyclone-v]   # added to the default folders
    terms:
      boards: [my-board]          # added to the group of the same name
    exceptions:
      src/legacy/top.vhd: wrapper kept until the board package exists
```

An exception is a path, a folder or a pattern (`fnmatch`) with its
justification. An exception without justification, or one that excuses
nothing, is a problem.
"""

import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.repo_walk import list_files

_DEFAULTS = Path(__file__).with_name("purity.yaml")
_LEFT = r"(?<![0-9A-Za-z])"
_NOT_A_LETTER = r"(?![^\W\d_])"
_SEPARATOR = "[-_ ]?"


class _Term:
    """One forbidden term, compiled.

    Parameters
    ----------
    group : str
        The group of the term, such as `boards`.
    text : str
        The term as written in the data; a trailing `*` drops the
        boundary on the right.
    """

    def __init__(self, group: str, text: str) -> None:
        self.group = group
        self.text = text
        body = text.removesuffix("*")
        parts = [
            _SEPARATOR if char in "- " else re.escape(char) for char in body
        ]
        right = "" if text.endswith("*") else _NOT_A_LETTER
        self.pattern = re.compile(
            f"{_LEFT}{''.join(parts)}{right}", re.IGNORECASE
        )


def _mapping(value: Any) -> dict[str, Any]:
    """Read a YAML value that must be a mapping.

    Parameters
    ----------
    value : Any
        The parsed value.

    Returns
    -------
    dict of str to Any
        The mapping; empty when the value is not one.
    """
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item for key, item in cast("dict[Any, Any]", value).items()
    }


def _strings(value: Any) -> list[str]:
    """Read a YAML value that must be a list of strings.

    Parameters
    ----------
    value : Any
        The parsed value.

    Returns
    -------
    list of str
        The items as strings; empty when the value is not a list.
    """
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast("list[Any]", value)]


def _load_defaults() -> dict[str, Any]:
    """Read the default data of the rule.

    Returns
    -------
    dict of str to Any
        The content of `purity.yaml`.
    """
    return _mapping(yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8")))


def _terms(default: dict[str, Any], extra: dict[str, Any]) -> list[_Term]:
    """Join the default terms with the ones of the repository.

    Parameters
    ----------
    default : dict of str to Any
        The data of `purity.yaml`.
    extra : dict of str to Any
        The `purity` subsection of the repository.

    Returns
    -------
    list of _Term
        The terms, each group in the order it was written.
    """
    groups = _mapping(default.get("terms"))
    for group, items in _mapping(extra.get("terms")).items():
        groups[group] = [*_strings(groups.get(group)), *_strings(items)]
    return [
        _Term(group, text)
        for group, items in groups.items()
        for text in _strings(items)
    ]


def _outside(
    root: Path, suffixes: tuple[str, ...], folders: frozenset[str]
) -> Iterator[Path]:
    """List the files the rule reads.

    Parameters
    ----------
    root : Path
        The repository root.
    suffixes : tuple of str
        The extensions to read.
    folders : frozenset of str
        The vendor folders, by lowercase name.

    Yields
    ------
    Path
        Each file with one of the suffixes that has no vendor folder in
        its path.
    """
    seen: set[Path] = set()
    for suffix in suffixes:
        for path in list_files(root, suffix):
            parents = {part.lower() for part in path.relative_to(root).parts}
            if path not in seen and not parents & folders:
                seen.add(path)
                yield path


def _hits(text: str, terms: list[_Term]) -> dict[str, tuple[int, int]]:
    """Find the forbidden terms in a text.

    Parameters
    ----------
    text : str
        The content of a file.
    terms : list of _Term
        The terms to look for.

    Returns
    -------
    dict of str to tuple of int and int
        For each term as `<group>:<term>`, the first line it appears on
        and how many times it appears.
    """
    found: dict[str, tuple[int, int]] = {}
    for term in terms:
        matches = list(term.pattern.finditer(text))
        if matches:
            first = text.count("\n", 0, matches[0].start()) + 1
            found[f"{term.group}:{term.text}"] = (first, len(matches))
    return found


def _excused(relative: str, exceptions: dict[str, str]) -> list[str]:
    """Find the exceptions that cover a file.

    Parameters
    ----------
    relative : str
        The path of the file, relative to the root.
    exceptions : dict of str to str
        The exceptions, by path, folder or pattern.

    Returns
    -------
    list of str
        The keys of the exceptions that match the file.
    """
    return [
        key
        for key in exceptions
        if fnmatchcase(relative, key)
        or relative.startswith(key.rstrip("/") + "/")
    ]


def rule_purity(root: Path, _kind: str, config: dict[str, Any]) -> list[str]:
    """Report board, family and vendor names outside the vendor folders.

    Parameters
    ----------
    root : Path
        The repository root.
    _kind : str
        The kind of repository; unused by this rule.
    config : dict of str to Any
        The `tree` section, with the optional `purity` subsection.

    Returns
    -------
    list of str
        One problem for each term in each file, with the first line and
        the count; one for each exception without justification and one
        for each exception that excuses no file.
    """
    default = _load_defaults()
    extra = _mapping(config.get("purity"))
    terms = _terms(default, extra)
    folders = frozenset(
        name.lower()
        for name in (
            *_strings(default.get("vendor_folders")),
            *_strings(extra.get("vendor_folders")),
        )
    )
    suffixes = tuple(
        dict.fromkeys(
            (
                *_strings(default.get("suffixes")),
                *_strings(extra.get("suffixes")),
            )
        )
    )
    exceptions = {
        str(key): str(why or "").strip()
        for key, why in {
            **_mapping(default.get("exceptions")),
            **_mapping(extra.get("exceptions")),
        }.items()
    }
    problems = [
        f"exception {key} has no justification"
        for key, why in sorted(exceptions.items())
        if not why
    ]
    used: set[str] = set()
    for path in sorted(_outside(root, suffixes, folders)):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = _hits(text, terms)
        if not hits:
            continue
        covering = _excused(relative, exceptions)
        used.update(covering)
        if covering:
            continue
        problems.extend(
            f"{relative}:{line}: {name} ({count}x) outside the vendor folders"
            for name, (line, count) in sorted(
                hits.items(), key=lambda item: item[1][0]
            )
        )
    problems.extend(
        f"exception {key} excuses no file"
        for key in sorted(set(exceptions) - used)
    )
    return problems
