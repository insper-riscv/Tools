"""Base shared by the local VSG rules of the project.

The VSG loads each file of this folder as a top-level module, so the
rules import this helper by its plain name and never import anything
else from `riscv_tools`: the VSG may run in an environment of its own.
"""

from typing import Any, NamedTuple, Protocol, override

from vsg import rule, violation

_NOT_CODE = frozenset(
    {"whitespace", "carriage_return", "blank_line", "comment"}
)


class VhdlFile(Protocol):
    """The part of the VSG file object that the rules read."""

    lAllObjects: list[Any]

    def get_lines(self) -> list[str]:
        """List the lines of the file, the first position empty."""
        ...


class Place:
    """Where a violation sits, in the form the VSG asks for."""

    def __init__(self, position: int, line: int, items: list[Any]) -> None:
        """Keep the tokens of the violation and where they start."""
        self.position = position
        self.line = line
        self.items = items

    def get_tokens(self) -> list[Any]:
        """List the tokens of the violation."""
        return self.items

    def get_start_index(self) -> int:
        """Give the position of the first token in the file."""
        return self.position

    def get_line_number(self) -> int:
        """Give the line of the first token."""
        return self.line

    def get_token_value(self) -> None:
        """Give no value: the rules never fix."""
        return


class Tok(NamedTuple):
    """One token of the file with the line it sits on.

    Attributes
    ----------
    position : int
        The position of the token in the token list of the file.
    line : int
        The 1-based line of the token.
    kind : str
        The VSG class of the token, as `<module>.<class>`.
    value : str
        The lower-case text of the token.
    """

    position: int
    line: int
    kind: str
    value: str


def scan(vhdl_file: VhdlFile) -> list[Tok]:
    """List the tokens of a parsed file with their lines.

    Parameters
    ----------
    vhdl_file : VhdlFile
        The file the VSG parsed.

    Returns
    -------
    list of Tok
        Every token in file order.
    """
    found: list[Tok] = []
    line = 1
    for index, item in enumerate(vhdl_file.lAllObjects):
        kind = type(item).__module__.rsplit(".", 1)[-1]
        kind += "." + type(item).__name__
        found.append(Tok(index, line, kind, str(item.get_value()).lower()))
        if kind == "parser.carriage_return":
            line += 1
    return found


def is_code(tok: Tok) -> bool:
    """Tell a token of code from white space and comments.

    Parameters
    ----------
    tok : Tok
        The token.

    Returns
    -------
    bool
        False for white space, line breaks, blank lines and comments.
    """
    return tok.kind.rsplit(".", 1)[-1] not in _NOT_CODE


class LocalRule(rule.Rule):
    """A rule of the project: it finds problems but never fixes them.

    Subclasses set `group` and `number` (the rule is `<group>_<number>`)
    and implement `find`, which returns `(line, message)` pairs.
    """

    group = ""
    number = ""

    def __init__(self) -> None:
        """Name the rule and put it in the first phase."""
        super().__init__()
        self.name = self.group
        self.identifier = self.number
        self.unique_id = f"{self.group}_{self.number}"
        self.phase = 1
        self.fixable = False

    def find(self, vhdl_file: VhdlFile) -> list[tuple[int, str]]:
        """Find the violations of the rule.

        Parameters
        ----------
        vhdl_file : VhdlFile
            The file the VSG parsed.

        Returns
        -------
        list of tuple of int and str
            The line and the message of each violation.
        """
        raise NotImplementedError

    @override
    def analyze(self, oFile: VhdlFile) -> None:
        """Record the violations of the rule in the file.

        Parameters
        ----------
        oFile : VhdlFile
            The file the VSG parsed.
        """
        found = self.find(oFile)
        if not found:
            return
        first: dict[int, Tok] = {}
        for tok in scan(oFile):
            first.setdefault(tok.line, tok)
        for line, message in found:
            tok = first.get(line, first[min(first)])
            at = Place(tok.position, line, [oFile.lAllObjects[tok.position]])
            self.add_violation(violation.New(line, at, message))
