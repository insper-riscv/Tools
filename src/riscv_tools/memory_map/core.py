"""Verify a platform's memory map against every copy written by hand.

A platform's memory map (region bases and sizes, the words the boot ROM
reserves at the top of RAM, the boot entry points, the peripheral windows)
is needed in many files: the linker flags, the boot ROM, the C runtime, the
VHDL, the Quartus IPs, the project's config.yaml. Each copy is only noticed
when it disagrees on the board. This module makes one YAML file the source
of truth and checks the copies against it.

The platform file has three parts:

- `regions`, `reserved`, `boot` and `peripherals`: the map itself.
- `checks`: where each copy lives and how to read the number out of it.

A check names a `file` (relative to the project root), reads one value out
of it (a regular expression with one capture group over the file's text, or
a dotted `yaml` path), and compares it with an `expect` expression over the
map's symbols. A check whose pattern matches nothing fails instead of
passing silently, so a copy that is reformatted out of a check's reach is
noticed.

Symbols are `<REGION>.base|size|end|words`, `<reserved>.base|size|end`,
`boot.entry`, `boot.wait_restart` and `<PERIPHERAL>.base|id`. Expressions
accept `+ - * /` (exact division only), `log2()` (exact), `clog2()` (rounded
up), hexadecimal, decimal, VHDL-based (`16#800#`) and suffixed (`30K`,
`0x800u`) numbers.
"""

import ast
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

_BINARY: dict[type, Callable[[int, int], int]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}
_UNITS = {"k": 1024, "m": 1024 * 1024}
_PERIPHERAL_ID_SHIFT = 28


@dataclass(frozen=True)
class Mismatch:
    """One disagreement (or unreadable copy) found by the check.

    Parameters
    ----------
    check : str
        The check's name, or `platform` for a problem in the map itself.
    file : str
        The file the value was read from ("" for the map itself).
    detail : str
        What disagrees: actual and expected values, or why it could not be read.
    """

    check: str
    file: str
    detail: str

    def __str__(self) -> str:
        """Format the mismatch as one line for the command's report.

        Returns
        -------
        str
            `check (file): detail`.
        """
        where = f" ({self.file})" if self.file else ""
        return f"{self.check}{where}: {self.detail}"


def evaluate(expr: str | int, names: dict[str, int] | None = None) -> int:
    """Evaluate a number or an arithmetic expression over the map's symbols.

    Parameters
    ----------
    expr : str or int
        A number in any of the accepted notations, or an expression.
    names : dict of {str: int}, optional
        Symbols, dotted as in `RAM.base`.

    Returns
    -------
    int
        The value.

    Raises
    ------
    ValueError
        If the expression is malformed, names an unknown symbol, uses an
        unsupported operation, or divides inexactly.
    """
    if isinstance(expr, int):
        return expr
    table = {k.replace(".", "__"): v for k, v in (names or {}).items()}
    text = re.sub(
        r"(\d+)#([0-9A-Fa-f_]+)#",
        lambda m: str(int(m.group(2).replace("_", ""), int(m.group(1)))),
        expr.strip(),
    )
    text = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b", r"\1", text)
    text = re.sub(
        r"\b(0[xX][0-9a-fA-F]+|\d+)([kKmM])\b",
        lambda m: f"({m.group(1)}*{_UNITS[m.group(2).lower()]})",
        text,
    )
    text = re.sub(r"([A-Za-z_]\w*)\.(\w+)", r"\1__\2", text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"cannot parse {expr!r}") from exc
    return _eval_node(tree.body, table, expr)


def _log2(func: str, value: int, source: str) -> int:
    """Compute `log2` (exact) or `clog2` (rounded up).

    Parameters
    ----------
    func : str
        `log2` or `clog2`.
    value : int
        The argument.
    source : str
        The original text, for error messages.

    Returns
    -------
    int
        The logarithm.

    Raises
    ------
    ValueError
        If `value` is not positive, or `log2` gets a non power of two.
    """
    if value <= 0:
        raise ValueError(f"{func} of a non positive value in {source!r}")
    if func == "clog2":
        return (value - 1).bit_length()
    if value & (value - 1):
        raise ValueError(f"log2 of a non power of two in {source!r}")
    return value.bit_length() - 1


def _eval_node(node: ast.expr, table: dict[str, int], source: str) -> int:
    """Evaluate one node of a parsed expression.

    Parameters
    ----------
    node : ast.expr
        The node.
    table : dict of {str: int}
        Symbols, with dots replaced by double underscores.
    source : str
        The original text, for error messages.

    Returns
    -------
    int
        The node's value.

    Raises
    ------
    ValueError
        On an unknown symbol, an unsupported operation or an inexact division.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in table:
            raise ValueError(f"unknown symbol {node.id.replace('__', '.')!r}")
        return table[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, table, source)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, table, source)
        right = _eval_node(node.right, table, source)
        if type(node.op) in _BINARY:
            return _BINARY[type(node.op)](left, right)
        if isinstance(node.op, ast.Div):
            if right == 0 or left % right:
                raise ValueError(f"inexact division in {source!r}")
            return left // right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"log2", "clog2"}
        and len(node.args) == 1
    ):
        return _log2(node.func.id, _eval_node(node.args[0], table, source), source)
    raise ValueError(f"unsupported expression {source!r}")


def load_platform(path: Path) -> dict[str, Any]:
    """Read a platform's YAML file.

    Parameters
    ----------
    path : Path
        The platform file.

    Returns
    -------
    dict of {str: Any}
        The parsed map and checks.

    Raises
    ------
    ValueError
        If the file is not a mapping.
    """
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a YAML mapping")
    return data  # pyright: ignore[reportUnknownVariableType]


def _list(platform: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Read a section of the platform that is a list of mappings.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        The section (`regions`, `peripherals`, `checks`).

    Returns
    -------
    list of dict of {str: Any}
        The section; empty when absent.
    """
    return cast("list[dict[str, Any]]", platform.get(key) or [])


def _dict(platform: dict[str, Any], key: str) -> dict[str, Any]:
    """Read a section of the platform that is a mapping.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        The section (`reserved`, `boot`).

    Returns
    -------
    dict of {str: Any}
        The section; empty when absent.
    """
    return cast("dict[str, Any]", platform.get(key) or {})


def symbols(platform: dict[str, Any]) -> dict[str, int]:
    """Flatten a platform's map into the symbols checks can name.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: int}
        `REGION.base|size|end|words`, `reserved.base|size|end`,
        `boot.entry|wait_restart`, `PERIPHERAL.base|id`.
    """
    out: dict[str, int] = {}
    for region in _list(platform, "regions"):
        base = evaluate(region["base"])
        size = evaluate(region["size"])
        name = region["name"]
        out |= {
            f"{name}.base": base,
            f"{name}.size": size,
            f"{name}.end": base + size,
            f"{name}.words": size // 4,
        }
    for name, item in _dict(platform, "reserved").items():
        base = evaluate(item["base"])
        size = evaluate(item["size"])
        out |= {f"{name}.base": base, f"{name}.size": size, f"{name}.end": base + size}
    for key, value in (_dict(platform, "boot")).items():
        out[f"boot.{key}"] = evaluate(value)
    for periph in _list(platform, "peripherals"):
        out[f"{periph['name']}.base"] = evaluate(periph["base"])
        out[f"{periph['name']}.id"] = int(periph["id"])
    return out


def _span(base: int, size: int) -> str:
    """Format an address range for messages.

    Parameters
    ----------
    base : int
        First address.
    size : int
        Length in bytes.

    Returns
    -------
    str
        `0xBASE-0xEND`.
    """
    return f"0x{base:X}-0x{base + size:X}"


def _overlaps(label: str, spans: list[tuple[str, int, int]]) -> list[Mismatch]:
    """Find pairs of ranges that overlap.

    Parameters
    ----------
    label : str
        What the ranges are, for the message (`regions`, `reserved`).
    spans : list of tuple of (str, int, int)
        `(name, base, size)` of each range.

    Returns
    -------
    list of Mismatch
        One per overlapping pair.
    """
    return [
        Mismatch("platform", "", f"{label} {name_a} and {name_b} overlap")
        for i, (name_a, base_a, size_a) in enumerate(spans)
        for name_b, base_b, size_b in spans[i + 1 :]
        if base_a < base_b + size_b and base_b < base_a + size_a
    ]


def _boot_problems(
    boot: dict[str, Any],
    spans: list[tuple[str, int, int]],
    execs: list[tuple[str, int, int]],
) -> list[Mismatch]:
    """Check the boot entry points against the regions.

    Parameters
    ----------
    boot : dict of {str: Any}
        The platform's `boot` section.
    spans : list of tuple of (str, int, int)
        Every region, in declaration order (the first is the boot ROM).
    execs : list of tuple of (str, int, int)
        The executable regions.

    Returns
    -------
    list of Mismatch
        `entry` outside every executable region, `wait_restart` outside the
        first region.
    """
    problems: list[Mismatch] = []
    if "entry" in boot and not any(
        b <= evaluate(boot["entry"]) < b + s for _, b, s in execs
    ):
        problems.append(
            Mismatch("platform", "", "boot.entry is not inside an executable region")
        )
    if "wait_restart" in boot and spans:
        name, base, size = spans[0]
        if not base <= evaluate(boot["wait_restart"]) < base + size:
            problems.append(
                Mismatch("platform", "", f"boot.wait_restart is not inside {name}")
            )
    return problems


def validate_platform(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the map's own consistency, before any copy is read.

    Regions must not overlap; reserved words must sit inside a RAM region and
    not overlap each other; the boot entry must be inside an executable region
    and `wait_restart` inside the first one; a peripheral's base must be
    `0x80000000 | id << 28` (the L2IP window convention).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        The problems; empty when the map is consistent.
    """
    regions = _list(platform, "regions")
    spans = [(r["name"], evaluate(r["base"]), evaluate(r["size"])) for r in regions]
    rams = [s for s, r in zip(spans, regions, strict=True) if r.get("kind") == "ram"]
    reserved = [
        (n, evaluate(v["base"]), evaluate(v["size"]))
        for n, v in _dict(platform, "reserved").items()
    ]
    execs = [s for s, r in zip(spans, regions, strict=True) if r.get("exec")]
    problems = _overlaps("regions", spans) + _overlaps("reserved", reserved)
    problems += [
        Mismatch(
            "platform",
            "",
            f"reserved {name} ({_span(base, size)}) is not inside a RAM region",
        )
        for name, base, size in reserved
        if not any(b <= base and base + size <= b + s for _, b, s in rams)
    ]
    problems += _boot_problems(_dict(platform, "boot"), spans, execs)
    for periph in _list(platform, "peripherals"):
        want = 0x80000000 | (int(periph["id"]) << _PERIPHERAL_ID_SHIFT)
        if evaluate(periph["base"]) != want:
            problems.append(
                Mismatch(
                    "platform",
                    "",
                    f"peripheral {periph['name']} base is not 0x{want:X} "
                    f"(bit31=1, id {periph['id']} in bits 30:28)",
                )
            )
    return problems


def _read_values(check: dict[str, Any], path: Path) -> list[str]:
    """Read the raw value text(s) a check points at.

    Parameters
    ----------
    check : dict of {str: Any}
        The check: `pattern` (one capture group) or `yaml` (dotted path).
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
            node = cast("dict[str, Any]", node)[key]
        return [str(node)]
    raise ValueError("check needs `pattern` or `yaml`")


def _run_check(
    check: dict[str, Any], root: Path, table: dict[str, int]
) -> list[Mismatch]:
    """Run one check.

    Parameters
    ----------
    check : dict of {str: Any}
        The check: `file`, `pattern` or `yaml`, `expect`, and optionally `name`,
        `optional` (skip when the file is absent).
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
        return [Mismatch(name, check["file"], "nothing matched: the copy moved")]
    problems: list[Mismatch] = []
    for text in raw:
        try:
            actual = evaluate(text)
        except ValueError as exc:
            problems.append(Mismatch(name, check["file"], str(exc)))
            continue
        if actual != expected:
            problems.append(
                Mismatch(
                    name,
                    check["file"],
                    f"found {text.strip()} (0x{actual:X}), "
                    f"expected {check['expect']} (0x{expected:X})",
                )
            )
    return problems


def check_memory_map(platform_path: Path, root: Path) -> tuple[int, list[Mismatch]]:
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
        How many checks ran, and the disagreements (empty when all agree).
    """
    platform = load_platform(platform_path)
    problems = validate_platform(platform)
    if problems:
        return 0, problems
    table = symbols(platform)
    checks = _list(platform, "checks")
    for check in checks:
        problems += _run_check(check, root, table)
    return len(checks), problems
