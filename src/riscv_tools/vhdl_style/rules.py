"""The style rules of the VHDL guide, one function for each.

Each rule takes a `Source` and returns the violations it finds as
`(line, message)` pairs. The rules follow the VHDL sections of the
Core's `CONTRIBUTING.md`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from riscv_tools.vhdl_style.declarations import (
    Declaration,
    closing,
    find_declarations,
    split_list,
)
from riscv_tools.vhdl_style.lexer import LineIndex, strip_code

HEADER_WIDTH = 72
ALLOWED_IEEE = frozenset({"std_logic_1164", "numeric_std"})
_PORT_PREFIX = {
    "in": "i_",
    "out": "o_",
    "buffer": "o_",
    "inout": "io_",
}
_DOCUMENTED = frozenset(
    {
        "generic",
        "port",
        "constant",
        "subtype",
        "type",
        "signal",
        "alias",
        "variable",
    }
)
_SEPARATOR = re.compile(r"^\s*--\s*(={3,}|-{3,})\s*$")
_HEADER_BAR = re.compile(r"^--\s?=+\s*$")
_COMMENT = re.compile(r"^\s*--")
_CONSTANT_NAME = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*")
_TYPE_NAME = re.compile(r"[a-z][a-z0-9_]*_t")
_COMPONENT = re.compile(r"\bcomponent\b", re.IGNORECASE)
_USE_IEEE = re.compile(r"\buse\s+ieee\.(\w+)", re.IGNORECASE)
_INSTANCE = re.compile(
    r"^\s*(\w+)\s*:\s*(?:entity|component|configuration)\b",
    re.IGNORECASE,
)
_PORT_MAP = re.compile(r"\bport\s+map\s*\(", re.IGNORECASE)


@dataclass(frozen=True)
class Source:
    """A VHDL file ready for the rules.

    Attributes
    ----------
    lines : list of str
        The lines of the file, as written.
    code : list of str
        The same lines without comments and literals.
    declarations : list of Declaration
        The declarations of the file.
    """

    lines: list[str]
    code: list[str]
    declarations: list[Declaration]


Violation = tuple[int, str]
Rule = Callable[[Source], list[Violation]]


def make_source(text: str) -> Source:
    """Prepare the text of a VHDL file for the rules.

    Parameters
    ----------
    text : str
        The content of the file.

    Returns
    -------
    Source
        The lines, the code and the declarations.
    """
    lines = text.splitlines()
    code = strip_code(lines)
    return Source(lines, code, find_declarations(code))


def _closes_header(lines: list[str]) -> bool:
    """Tell whether the comment block after the first line is a header.

    Parameters
    ----------
    lines : list of str
        The lines of the file after the opening bar.

    Returns
    -------
    bool
        True when a closing bar follows at least one line of text,
        with nothing but comments in between.
    """
    body = 0
    for line in lines:
        if _HEADER_BAR.match(line):
            return body > 0
        if not _COMMENT.match(line):
            return False
        body += bool(line.strip().removeprefix("--").strip())
    return False


def rule_header(source: Source) -> list[Violation]:
    """Require the header block of 72 columns at the top of the file.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation when the header is missing or incomplete.
    """
    lines = source.lines
    opens = (
        bool(lines)
        and bool(_HEADER_BAR.match(lines[0]))
        and len(lines[0].rstrip()) >= HEADER_WIDTH
    )
    if opens and _closes_header(lines[1:]):
        return []
    return [
        (
            1,
            "the file must open with a header: a line of `=` of at least "
            f"{HEADER_WIDTH} columns, the description and a closing line",
        )
    ]


def rule_libraries(source: Source) -> list[Violation]:
    """Allow only `std_logic_1164` and `numeric_std` from IEEE.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each other IEEE package.
    """
    found: list[Violation] = []
    for number, line in enumerate(source.code, start=1):
        found.extend(
            (number, f"ieee.{match.group(1)} is not allowed")
            for match in _USE_IEEE.finditer(line)
            if match.group(1).lower() not in ALLOWED_IEEE
        )
    return found


def rule_component(source: Source) -> list[Violation]:
    """Forbid `component` declarations; instantiate the entity directly.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each line that names a component.
    """
    return [
        (number, "use `u_x : entity work.x`, with no `component`")
        for number, line in enumerate(source.code, start=1)
        if _COMPONENT.search(line)
    ]


def rule_port_map(source: Source) -> list[Violation]:
    """Require every association of a `port map` to be by name.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each positional association.
    """
    index = LineIndex(source.code)
    found: list[Violation] = []
    for match in _PORT_MAP.finditer(index.text):
        opening = match.end() - 1
        end = closing(index.text, opening)
        found.extend(
            (
                index.line_of(offset),
                "associate the port by name (`i_x => sig`)",
            )
            for offset, piece in split_list(index.text, opening + 1, end, ",")
            if "=>" not in piece
        )
    return found


def rule_ports(source: Source) -> list[Violation]:
    """Require the `i_`, `o_` and `io_` prefix on every port.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each port without the prefix of its mode.
    """
    found: list[Violation] = []
    for declaration in source.declarations:
        prefix = _PORT_PREFIX.get(declaration.mode)
        if declaration.kind != "port" or prefix is None:
            continue
        found.extend(
            (declaration.line, f"port {name} must start with {prefix}")
            for name in declaration.names
            if not name.lower().startswith(prefix)
        )
    return found


def rule_docstrings(source: Source) -> list[Violation]:
    """Require a comment on the line above each declaration.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each declaration without its comment.
    """
    found: list[Violation] = []
    for declaration in source.declarations:
        if declaration.kind not in _DOCUMENTED:
            continue
        above = (
            source.lines[declaration.line - 2] if declaration.line > 1 else ""
        )
        if not _COMMENT.match(above) or _SEPARATOR.match(above):
            names = ", ".join(declaration.names)
            found.append(
                (
                    declaration.line,
                    f"{declaration.kind} {names} needs a comment on the "
                    "line above",
                )
            )
    return found


def _bad_name(declaration: Declaration) -> str:
    """Name the convention a declaration breaks, if any.

    Parameters
    ----------
    declaration : Declaration
        The declaration.

    Returns
    -------
    str
        The message, or an empty string when the names conform.
    """
    if declaration.kind == "constant":
        pattern, expected = _CONSTANT_NAME, "UPPER_SNAKE_CASE"
    elif declaration.kind in {"type", "subtype"}:
        pattern, expected = _TYPE_NAME, "snake_case with the suffix _t"
    else:
        return ""
    wrong = [name for name in declaration.names if not pattern.fullmatch(name)]
    if not wrong:
        return ""
    return f"{declaration.kind} {', '.join(wrong)} must be {expected}"


def rule_naming(source: Source) -> list[Violation]:
    """Require UPPER_SNAKE_CASE constants, `_t` types and `u_` labels.

    Parameters
    ----------
    source : Source
        The file.

    Returns
    -------
    list of tuple of int and str
        One violation for each name that breaks its convention.
    """
    found: list[Violation] = []
    for declaration in source.declarations:
        message = _bad_name(declaration)
        if message:
            found.append((declaration.line, message))
    for number, line in enumerate(source.code, start=1):
        match = _INSTANCE.match(line)
        if match and not match.group(1).lower().startswith("u_"):
            found.append(
                (number, f"instance label {match.group(1)} must start with u_")
            )
    return found


RULES: dict[str, Rule] = {
    "header": rule_header,
    "libraries": rule_libraries,
    "component": rule_component,
    "port-map": rule_port_map,
    "ports": rule_ports,
    "docstrings": rule_docstrings,
    "naming": rule_naming,
}
