"""Find the declarations of a VHDL file that the style rules inspect.

A declaration is a `generic`, a `port`, a `constant`, a `signal`, a
`variable`, an `alias`, a `type` or a `subtype`. Generics and ports sit
in parenthesised lists, found by matching the parentheses; the others
start a line outside any parentheses, which leaves out the parameters of
a function.
"""

import re
from dataclasses import dataclass

from riscv_tools.vhdl_style.lexer import LineIndex

_CLAUSE = re.compile(r"\b(generic|port)\s*\(", re.IGNORECASE)
_ELEMENT = re.compile(
    r"(?:(?:constant|signal)\s+)?"
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*"
    r"(?:(in|out|inout|buffer|linkage)\b)?",
    re.IGNORECASE,
)
_STATEMENT = re.compile(
    r"\s*(?:shared\s+)?(constant|signal|variable|alias|subtype|type)\s+"
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Declaration:
    """One declaration found in a file.

    Attributes
    ----------
    kind : str
        `generic`, `port`, `constant`, `signal`, `variable`, `alias`,
        `type` or `subtype`.
    names : tuple of str
        The declared names.
    line : int
        The 1-based line where the declaration starts.
    mode : str
        The port mode (`in`, `out`, ...), empty for the other kinds.
    """

    kind: str
    names: tuple[str, ...]
    line: int
    mode: str = ""


def _names(text: str) -> tuple[str, ...]:
    """Split a comma separated list of identifiers.

    Parameters
    ----------
    text : str
        The identifiers, such as `a, b`.

    Returns
    -------
    tuple of str
        The identifiers.
    """
    return tuple(name.strip() for name in text.split(","))


def closing(text: str, opening: int) -> int:
    """Find the parenthesis that closes the one at `opening`.

    Parameters
    ----------
    text : str
        The stripped code.
    opening : int
        The index of an opening parenthesis.

    Returns
    -------
    int
        The index of the matching closing parenthesis, or the text
        length when it never closes.
    """
    depth = 0
    for index in range(opening, len(text)):
        depth += (text[index] == "(") - (text[index] == ")")
        if depth == 0:
            return index
    return len(text)


def split_list(
    text: str, start: int, end: int, separator: str = ";"
) -> list[tuple[int, str]]:
    """Split a parenthesised list at its top level separators.

    Parameters
    ----------
    text : str
        The stripped code.
    start : int
        The index just after the opening parenthesis.
    end : int
        The index of the closing parenthesis.
    separator : str, optional
        The character that separates the elements, by default `;`.

    Returns
    -------
    list of tuple of int and str
        The offset of the first character of each element, and the
        element text; empty elements are dropped.
    """
    found: list[tuple[int, str]] = []
    depth = 0
    begin = start
    for index in range(start, end + 1):
        char = text[index] if index < end else separator
        depth += (char == "(") - (char == ")")
        if char == separator and depth == 0:
            piece = text[begin:index]
            lead = len(piece) - len(piece.lstrip())
            if piece.strip():
                found.append((begin + lead, piece.strip()))
            begin = index + 1
    return found


def _clause_declarations(index: LineIndex) -> list[Declaration]:
    """Find the generics and the ports.

    Parameters
    ----------
    index : LineIndex
        The stripped code.

    Returns
    -------
    list of Declaration
        One per element of each `generic (...)` and `port (...)`.
    """
    found: list[Declaration] = []
    for clause in _CLAUSE.finditer(index.text):
        opening = clause.end() - 1
        end = closing(index.text, opening)
        kind = clause.group(1).lower()
        for offset, element in split_list(index.text, opening + 1, end):
            match = _ELEMENT.match(element)
            if match:
                mode = (match.group(2) or "").lower() if kind == "port" else ""
                found.append(
                    Declaration(
                        kind,
                        _names(match.group(1)),
                        index.line_of(offset),
                        mode,
                    )
                )
    return found


def _statement_declarations(code: list[str]) -> list[Declaration]:
    """Find the declarations that start a line outside parentheses.

    Parameters
    ----------
    code : list of str
        The stripped lines.

    Returns
    -------
    list of Declaration
        One per `constant`, `signal`, `variable`, `alias`, `type` and
        `subtype` statement.
    """
    found: list[Declaration] = []
    depth = 0
    for number, line in enumerate(code, start=1):
        match = _STATEMENT.match(line) if depth == 0 else None
        if match:
            found.append(
                Declaration(
                    match.group(1).lower(), _names(match.group(2)), number
                )
            )
        depth += line.count("(") - line.count(")")
    return found


def find_declarations(code: list[str]) -> list[Declaration]:
    """Find every declaration the style rules inspect.

    Parameters
    ----------
    code : list of str
        The stripped lines of a file.

    Returns
    -------
    list of Declaration
        The declarations, in file order.
    """
    found = _clause_declarations(LineIndex(code))
    found.extend(_statement_declarations(code))
    return sorted(found, key=lambda declaration: declaration.line)
