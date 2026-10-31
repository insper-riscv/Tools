"""Read each hand-written copy of the memory map and compare it."""

import re
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.memory_map.core import (
    Mismatch,
    load_platform,
    platform_list,
    symbols,
)
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.validation import hex_text, validate_platform


def _read_values(check: dict[str, Any], path: Path) -> list[str]:
    """Read the raw value text(s) a check points at.

    Parameters
    ----------
    check : dict of {str: Any}
        The check: `pattern` (one capture group) or `yaml` (dotted
        path).
    path : Path
        The file to read.

    Returns
    -------
    list of str
        One entry per match; empty when nothing matched.

    Raises
    ------
    ValueError
        If the check has neither `pattern` nor `yaml`.
    """
    if "pattern" in check:
        pattern = re.compile(check["pattern"], re.MULTILINE)
        return [m.group(1) for m in pattern.finditer(path.read_text())]
    if "yaml" in check:
        node: Any = yaml.safe_load(path.read_text())
        for key in str(check["yaml"]).split("."):
            if not isinstance(node, dict) or key not in node:
                return []
            node = cast(dict[str, Any], node)[key]
        return [str(node)]
    raise ValueError("check needs `pattern` or `yaml`")


def _run_check(
    check: dict[str, Any], root: Path, table: dict[str, int]
) -> list[Mismatch]:
    """Run one check.

    Parameters
    ----------
    check : dict of {str: Any}
        The check: `file`, `pattern` or `yaml`, `expect`, and optionally
        `name`, `optional` (skip when the file is absent).
    root : Path
        The project root the file is relative to.
    table : dict of {str: int}
        The map's symbols.

    Returns
    -------
    list of Mismatch
        Empty when every match equals the expected value.
    """
    name = str(check.get("name") or f"{check['file']}: {check['expect']}")
    path = root / check["file"]
    if not path.is_file():
        if check.get("optional"):
            return []
        return [Mismatch(name, check["file"], "file not found")]
    try:
        expected = evaluate(check["expect"], table)
        raw = _read_values(check, path)
    except (ValueError, OSError, re.error, yaml.YAMLError) as exc:
        return [Mismatch(name, check["file"], str(exc))]
    if not raw:
        return [
            Mismatch(name, check["file"], "nothing matched: the copy moved")
        ]
    problems: list[Mismatch] = []
    for text in raw:
        problem = _compare(check, name, text, expected)
        if problem is not None:
            problems.append(problem)
    return problems


def _compare(
    check: dict[str, Any], name: str, text: str, expected: int
) -> Mismatch | None:
    """Compare one value read from a file with the expected one.

    Parameters
    ----------
    check : dict of {str: Any}
        The check, for its `file` and `expect`.
    name : str
        The check's name.
    text : str
        The raw value text.
    expected : int
        The expected value.

    Returns
    -------
    Mismatch or None
        The disagreement, or None when the values are equal.
    """
    try:
        actual = evaluate(text)
    except ValueError as exc:
        return Mismatch(name, check["file"], str(exc))
    if actual == expected:
        return None
    return Mismatch(
        name,
        check["file"],
        f"found {text.strip()} ({hex_text(actual)}), "
        f"expected {check['expect']} ({hex_text(expected)})",
    )


def check_memory_map(
    platform_path: Path, root: Path
) -> tuple[int, list[Mismatch]]:
    """Validate a platform's map and check every copy against it.

    Parameters
    ----------
    platform_path : Path
        The platform YAML.
    root : Path
        The project root the checks' files are relative to.

    Returns
    -------
    tuple of (int, list of Mismatch)
        How many checks ran, and the disagreements (empty when all
        agree).
    """
    platform = load_platform(platform_path)
    problems = validate_platform(platform)
    if problems:
        return 0, problems
    table = symbols(platform)
    checks = platform_list(platform, "checks")
    for check in checks:
        problems += _run_check(check, root, table)
    return len(checks), problems
