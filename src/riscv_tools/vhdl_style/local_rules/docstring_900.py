"""Rule docstring_900: a comment above each declaration."""

import re
from typing import override

from capstone_rule import LocalRule, Tok, VhdlFile, is_code, scan

_COMMENT = re.compile(r"^\s*--")
_SEPARATOR = re.compile(r"^\s*--\s*(={3,}|-{3,})\s*$")
_STATEMENTS = {
    "signal_declaration.signal_keyword": "signal",
    "constant_declaration.constant_keyword": "constant",
    "variable_declaration.variable_keyword": "variable",
    "alias_declaration.alias_keyword": "alias",
    "subtype_declaration.subtype_keyword": "subtype",
    "full_type_declaration.type_keyword": "type",
}
_OPENS = {
    "generic_clause.open_parenthesis": "generic",
    "port_clause.open_parenthesis": "port",
}
_CLOSES = frozenset(
    {"generic_clause.close_parenthesis", "port_clause.close_parenthesis"}
)


def _elements(tokens: list[Tok]) -> list[tuple[int, str]]:
    """Find the first line of each generic and port.

    Parameters
    ----------
    tokens : list of Tok
        The tokens of the file.

    Returns
    -------
    list of tuple of int and str
        The line and the clause (`generic` or `port`) of each element.
    """
    found: list[tuple[int, str]] = []
    clause = ""
    fresh = False
    for tok in tokens:
        if tok.kind in _OPENS:
            clause, fresh = _OPENS[tok.kind], True
        elif tok.kind in _CLOSES:
            clause = ""
        elif clause and tok.kind == "interface_list.semicolon":
            fresh = True
        elif clause and fresh and is_code(tok):
            found.append((tok.line, clause))
            fresh = False
    return found


def _statements(tokens: list[Tok]) -> list[tuple[int, str]]:
    """Find the line of each declaration written as a statement.

    Parameters
    ----------
    tokens : list of Tok
        The tokens of the file.

    Returns
    -------
    list of tuple of int and str
        The line and the kind of each declaration.
    """
    return [
        (tok.line, _STATEMENTS[tok.kind])
        for tok in tokens
        if tok.kind in _STATEMENTS
    ]


class rule_docstring_900(LocalRule):
    """Require a comment on the line above each declaration.

    Covers `generic`, `port`, `constant`, `subtype`, `type`, `signal`,
    `alias` and `variable`. A comment at the end of the line does not
    count, and neither does a line of separator (CONTRIBUTING, section
    4.2). The parameters of a function or procedure are not declarations
    for this rule.
    """

    group = "docstring"
    number = "900"

    @override
    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Report each declaration without its comment above.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each declaration.
        """
        lines = vhdl_file.get_lines()
        tokens = scan(vhdl_file)
        found: list[tuple[int, str]] = []
        for line, kind in sorted(_elements(tokens) + _statements(tokens)):
            above = lines[line - 1] if line > 1 else ""
            if not _COMMENT.match(above) or _SEPARATOR.match(above):
                found.append(
                    (
                        line,
                        f"A declaração de {kind} precisa de um comentário "
                        "próprio na linha acima (CONTRIBUTING, seção 4.2)",
                    )
                )
        return found
