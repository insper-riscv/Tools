"""Evaluate the integer subset of SystemVerilog the IP-XACT files use.

IEEE Std 1685-2022 writes every expression in the SystemVerilog syntax
(Annex E) and requires it to be well formed (SCR 5.17), to name only
existing parameters (SCR 5.18) and not to refer to itself (SCR 5.19).
The subset is the one the extraction produces: integer and sized
literals, parameter names, parentheses, the arithmetic, relational and
logical operators, the conditional operator and `$clog2` (E.5.1).
"""

import operator
import re
from collections.abc import Callable, Iterator, Mapping


def _div(left: int, right: int) -> int:
    """Divide as SystemVerilog does, truncating toward zero."""
    quotient = abs(left) // abs(right)
    return quotient if (left < 0) == (right < 0) else -quotient


TOKEN = re.compile(
    r"\s*(?:(\d+'[sS]?[bBoOdDhH][0-9a-fA-F_]+)|(\d+)"
    r"|(\$clog2|[A-Za-z_]\w*)|(\*\*|&&|\|\||==|!=|<=|>=|[-+*/%()<>?:]))"
)
BASES = {"b": 2, "o": 8, "d": 10, "h": 16}
LEVELS: tuple[dict[str, Callable[[int, int], int]], ...] = (
    {"||": lambda a, b: int(bool(a or b))},
    {"&&": lambda a, b: int(bool(a and b))},
    {
        "==": lambda a, b: int(a == b),
        "!=": lambda a, b: int(a != b),
    },
    {
        "<": lambda a, b: int(a < b),
        "<=": lambda a, b: int(a <= b),
        ">": lambda a, b: int(a > b),
        ">=": lambda a, b: int(a >= b),
    },
    {"+": operator.add, "-": operator.sub},
    {
        "*": operator.mul,
        "/": _div,
        "%": lambda a, b: a - b * _div(a, b),
    },
)


class ExpressionError(ValueError):
    """An expression that is malformed or cannot be evaluated."""


def _tokens(text: str) -> list[str]:
    """Split an expression into tokens.

    Raises
    ------
    ExpressionError
        If a character belongs to no token.
    """
    found: list[str] = []
    position = 0
    stripped = text.rstrip()
    while position < len(stripped):
        match = TOKEN.match(stripped, position)
        if match is None:
            raise ExpressionError(f"unexpected character in {text!r}")
        found.append(match.group().strip())
        position = match.end()
    return found


def identifiers(text: str) -> Iterator[str]:
    """List the names an expression uses.

    Parameters
    ----------
    text : str
        The expression.

    Yields
    ------
    str
        Each identifier, in order of appearance.
    """
    for token in _tokens(text):
        if re.fullmatch(r"[A-Za-z_]\w*", token):
            yield token


def _sized(token: str) -> int:
    """Read a sized literal such as `8'hFF`."""
    _, _, rest = token.partition("'")
    rest = rest.lstrip("sS")
    return int(rest[1:].replace("_", ""), BASES[rest[0].lower()])


class _Parser:
    """A recursive-descent evaluator over the tokens."""

    def __init__(
        self, tokens: list[str], lookup: Callable[[str], int]
    ) -> None:
        """Start at the first token.

        Parameters
        ----------
        tokens : list of str
            The tokens of the expression.
        lookup : Callable
            Gives the value of a parameter name.
        """
        self.tokens = tokens
        self.lookup = lookup
        self.position = 0

    def peek(self) -> str:
        """Give the next token, or an empty string at the end."""
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return ""

    def take(self, expected: str | None = None) -> str:
        """Consume the next token, which must be the expected one."""
        token = self.peek()
        if not token or (expected is not None and token != expected):
            raise ExpressionError(f"expected {expected or 'a token'}")
        self.position += 1
        return token

    def ternary(self) -> int:
        """Parse the conditional operator."""
        cond = self.binary(0)
        if self.peek() != "?":
            return cond
        self.take("?")
        yes = self.ternary()
        self.take(":")
        no = self.ternary()
        return yes if cond else no

    def binary(self, level: int) -> int:
        """Parse a left-associative binary level."""
        if level == len(LEVELS):
            return self.power()
        value = self.binary(level + 1)
        while self.peek() in LEVELS[level]:
            func = LEVELS[level][self.take()]
            value = func(value, self.binary(level + 1))
        return value

    def power(self) -> int:
        """Parse the right-associative power operator."""
        base = self.unary()
        if self.peek() == "**":
            self.take()
            return base ** self.power()
        return base

    def unary(self) -> int:
        """Parse a sign."""
        if self.peek() in ("-", "+"):
            sign = self.take()
            value = self.unary()
            return -value if sign == "-" else value
        return self.atom()

    def atom(self) -> int:
        """Parse a literal, a name or a parenthesis."""
        item = self.take()
        if item == "$clog2":
            self.take("(")
            value = self.ternary()
            self.take(")")
            return max(value - 1, 0).bit_length()
        if item == "(":
            value = self.ternary()
            self.take(")")
            return value
        if "'" in item:
            return _sized(item)
        if item.isdigit():
            return int(item)
        if re.fullmatch(r"[A-Za-z_]\w*", item):
            return self.lookup(item)
        raise ExpressionError(f"unexpected {item!r}")


def evaluate(text: str, lookup: Callable[[str], int]) -> int:
    """Evaluate an expression.

    Parameters
    ----------
    text : str
        The expression.
    lookup : Callable
        Gives the value of a parameter name; it raises `ExpressionError`
        for a name that does not exist or whose value is circular.

    Returns
    -------
    int
        The value.

    Raises
    ------
    ExpressionError
        If the expression is malformed or cannot be evaluated.
    """
    parser = _Parser(_tokens(text), lookup)
    try:
        value = parser.ternary()
    except (ZeroDivisionError, OverflowError) as error:
        raise ExpressionError(f"{text!r}: {error}") from error
    if parser.peek():
        raise ExpressionError(f"{text!r}: trailing {parser.peek()!r}")
    return value


def evaluate_with(text: str, names: Mapping[str, int]) -> int:
    """Evaluate an expression whose names have known values."""

    def lookup(name: str) -> int:
        if name not in names:
            raise ExpressionError(f"{name!r} is not a parameter")
        return names[name]

    return evaluate(text, lookup)
