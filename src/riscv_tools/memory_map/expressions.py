"""Evaluate the arithmetic expressions of a memory map file."""

import ast
import operator
import re
from collections.abc import Callable

_BINARY: dict[type, Callable[[int, int], int]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


_UNITS = {"k": 1024, "m": 1024 * 1024}


_LOG_FUNCTIONS = frozenset({"log2", "clog2"})


def evaluate(expr: str | int, names: dict[str, int] | None = None) -> int:
    """Evaluate a number or an arithmetic expression.

    The expression ranges over the symbols of the map.

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
        On an unknown symbol, an unsupported operation or an inexact
        division.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        return _eval_name(node, table)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, table, source)
    if isinstance(node, ast.BinOp):
        return _eval_binop(node, table, source)
    if isinstance(node, ast.Call):
        return _eval_call(node, table, source)
    raise ValueError(f"unsupported expression {source!r}")


def _eval_name(node: ast.Name, table: dict[str, int]) -> int:
    """Look a symbol up.

    Parameters
    ----------
    node : ast.Name
        The symbol node.
    table : dict of {str: int}
        Symbols, with dots replaced by double underscores.

    Returns
    -------
    int
        The symbol's value.

    Raises
    ------
    ValueError
        If the symbol is unknown.
    """
    if node.id not in table:
        raise ValueError(f"unknown symbol {node.id.replace('__', '.')!r}")
    return table[node.id]


def _eval_binop(node: ast.BinOp, table: dict[str, int], source: str) -> int:
    """Evaluate a binary operation.

    Parameters
    ----------
    node : ast.BinOp
        The operation node.
    table : dict of {str: int}
        Symbols, with dots replaced by double underscores.
    source : str
        The original text, for error messages.

    Returns
    -------
    int
        The operation's value.

    Raises
    ------
    ValueError
        On an unsupported operator or an inexact division.
    """
    left = _eval_node(node.left, table, source)
    right = _eval_node(node.right, table, source)
    if type(node.op) in _BINARY:
        return _BINARY[type(node.op)](left, right)
    if isinstance(node.op, ast.Div):
        if right == 0 or left % right:
            raise ValueError(f"inexact division in {source!r}")
        return left // right
    raise ValueError(f"unsupported expression {source!r}")


def _eval_call(node: ast.Call, table: dict[str, int], source: str) -> int:
    """Evaluate a `log2` or `clog2` call.

    Parameters
    ----------
    node : ast.Call
        The call node.
    table : dict of {str: int}
        Symbols, with dots replaced by double underscores.
    source : str
        The original text, for error messages.

    Returns
    -------
    int
        The call's value.

    Raises
    ------
    ValueError
        If the call is not `log2`/`clog2` of one argument.
    """
    if (
        isinstance(node.func, ast.Name)
        and node.func.id in _LOG_FUNCTIONS
        and len(node.args) == 1
    ):
        return _log2(
            node.func.id, _eval_node(node.args[0], table, source), source
        )
    raise ValueError(f"unsupported expression {source!r}")
