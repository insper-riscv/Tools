"""Turn an expression of the GHDL syntax tree into a SystemVerilog one.

IP-XACT writes every expression in the SystemVerilog syntax (IEEE Std
1685-2022, clause C.6 and Annex E), and the only identifiers it allows
are parameter identifiers (rule SCR 5.18). A VHDL expression of a port
limit is therefore rendered with the generics as identifiers; a
constant of a package is folded to its value, and a construct that has
no such form is refused, so the XML never says something the VHDL does
not.
"""

import operator
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import NamedTuple
from xml.etree.ElementTree import Element

from riscv_tools.ipxact.model import ExtractError

Index = dict[str, Element]
PICK_ARGUMENTS = 3


class Value(NamedTuple):
    """A rendered expression.

    Parameters
    ----------
    text : str
        The SystemVerilog text.
    number : int or None
        The value, when the expression has no generic in it.
    """

    text: str
    number: int | None


def _div(left: int, right: int) -> int:
    """Divide as VHDL does, truncating toward zero."""
    quotient = abs(left) // abs(right)
    return quotient if (left < 0) == (right < 0) else -quotient


def _rem(left: int, right: int) -> int:
    """Take the remainder with the sign of the dividend (VHDL `rem`)."""
    return left - right * _div(left, right)


BINARY: dict[str, tuple[str, Callable[[int, int], int]]] = {
    "addition_operator": ("+", operator.add),
    "substraction_operator": ("-", operator.sub),
    "multiplication_operator": ("*", operator.mul),
    "division_operator": ("/", _div),
    "remainder_operator": ("%", _rem),
    "modulus_operator": ("%", operator.mod),
    "exponentiation_operator": ("**", lambda a, b: a**b),
}
UNARY: dict[str, tuple[str, Callable[[int], int]]] = {
    "negation_operator": ("-", operator.neg),
    "identity_operator": ("+", operator.pos),
}
LOGIC: dict[str, tuple[str, Callable[[int, int], int]]] = {
    "and_operator": ("&&", lambda a, b: int(bool(a and b))),
    "or_operator": ("||", lambda a, b: int(bool(a or b))),
    "equality_operator": ("==", lambda a, b: int(a == b)),
    "inequality_operator": ("!=", lambda a, b: int(a != b)),
    "greater_than_operator": (">", lambda a, b: int(a > b)),
    "greater_than_or_equal_operator": (">=", lambda a, b: int(a >= b)),
    "less_than_operator": ("<", lambda a, b: int(a < b)),
    "less_than_or_equal_operator": ("<=", lambda a, b: int(a <= b)),
}
# Functions of the shared utilities whose body is a loop; both give the
# ceiling of the base-2 logarithm, which is the `$clog2` of E.5.1.
CLOG2 = frozenset({"log2_ceil", "log2_exact"})
MAX_DEPTH = 16


class Context(NamedTuple):
    """What a name in the expression may refer to.

    Parameters
    ----------
    nodes : dict of str to Element
        Every element of the tree that has an `id`.
    entity : str
        The `id` of the entity whose generics are the identifiers.
    env : dict of str to Value
        The value of each formal parameter of the function being
        expanded, by the `id` of its declaration.
    depth : int
        How many function bodies are being expanded.
    """

    nodes: Index
    entity: str
    env: Mapping[str, Value] = MappingProxyType({})
    depth: int = 0


def target(ctx: Context, element: Element, tag: str) -> Element | None:
    """Follow the `ref` of a child to the element it points at."""
    node = element.find(tag)
    if node is None:
        return None
    return ctx.nodes.get(node.get("ref", ""))


def _where(element: Element) -> str:
    """Describe the place of an element in the source."""
    return (
        f"{element.get('file', '?')}:{element.get('line', '?')}:"
        f"{element.get('col', '?')}"
    )


def refuse(element: Element, why: str) -> ExtractError:
    """Build the error for a construct that cannot be rendered."""
    return ExtractError(f"{_where(element)}: {why}")


def _literal(element: Element) -> Value:
    """Render an integer literal."""
    number = int(element.get("value", "0").strip())
    return Value(str(number), number)


def _enumeration(element: Element) -> Value:
    """Render `true` and `false`, the only enumerations accepted."""
    word = element.get("identifier", "").lower()
    if word in ("true", "false"):
        number = int(word == "true")
        return Value(str(number), number)
    raise refuse(element, f"enumeration literal {word!r} has no form")


def _name(ctx: Context, element: Element) -> Value:
    """Render a name: a generic stays, a constant folds to its value."""
    decl = target(ctx, element, "named_entity")
    if decl is None:
        raise refuse(element, "name without a declaration")
    kind = decl.get("kind", "")
    if decl.get("id", "") in ctx.env:
        return ctx.env[decl.get("id", "")]
    if kind == "enumeration_literal":
        return _enumeration(decl)
    if kind == "interface_constant_declaration":
        parent = decl.find("parent")
        if parent is not None and parent.get("ref") == ctx.entity:
            return Value(decl.get("identifier", ""), None)
        raise refuse(element, "constant of a subprogram or another unit")
    if kind == "constant_declaration":
        return _constant(ctx, element, decl)
    raise refuse(element, f"name of a {kind} in a limit")


def _constant(ctx: Context, element: Element, decl: Element) -> Value:
    """Fold a constant of a package to its value."""
    default = decl.find("default_value")
    if default is None:
        raise refuse(element, "deferred constant has no value to fold")
    value = render(ctx, default)
    if value.number is None:
        raise refuse(element, "constant that depends on a generic")
    return value


def _choose(cond: Value, yes: Value, no: Value) -> Value:
    """Render a conditional expression, folded when the condition is."""
    if cond.number is not None:
        return yes if cond.number else no
    return Value(f"({cond.text} ? {yes.text} : {no.text})", None)


def _statements(ctx: Context, chain: list[Element]) -> Value:
    """Render the statements of a function body as one expression.

    A body is a `return`, or an `if` without `else` whose branch
    returns and that is followed by the rest of the body; an assertion
    is a precondition and does not change the value.
    """
    for position, statement in enumerate(chain):
        if statement.get("kind") == "assertion_statement":
            continue
        return _statement(ctx, statement, chain[position + 1 :])
    raise refuse(chain[-1] if chain else _EMPTY, "function without a return")


def _statement(ctx: Context, statement: Element, rest: list[Element]) -> Value:
    """Render a `return`, or an `if` and the rest of the body."""
    kind = statement.get("kind", "")
    if kind == "return_statement":
        return render(ctx, _operand(statement, "expression"))
    if kind == "if_statement" and statement.find("else_clause") is None:
        branch = statement.find("sequential_statement_chain")
        cond = render(ctx, _operand(statement, "condition"))
        then = _statements(ctx, [] if branch is None else list(branch))
        return _choose(cond, then, _statements(ctx, rest))
    raise refuse(statement, f"statement {kind} cannot be expanded")


_EMPTY = Element("none")


def _expand(ctx: Context, element: Element, decl: Element) -> Value:
    """Expand a call of a function whose body is a few returns."""
    if ctx.depth >= MAX_DEPTH:
        raise refuse(element, "function calls nested too deep")
    body = ctx.nodes.get(f"body:{decl.get('id', '')}")
    formals = decl.findall("interface_declaration_chain/el")
    actuals = element.findall("parameter_association_chain/el/actual")
    if body is None or len(formals) != len(actuals):
        raise refuse(element, "call of a function with no body to expand")
    env = {
        formal.get("id", ""): render(ctx, actual)
        for formal, actual in zip(formals, actuals, strict=True)
    }
    inner = ctx._replace(env=env, depth=ctx.depth + 1)
    chain = body.find("sequential_statement_chain")
    return _statements(inner, [] if chain is None else list(chain))


def _call(ctx: Context, element: Element) -> Value:
    """Render a function call: `pick`, `$clog2` or an expanded body."""
    decl = target(ctx, element, "implementation")
    name = "" if decl is None else decl.get("identifier", "").lower()
    actuals = element.findall("parameter_association_chain/el/actual")
    if decl is None:
        raise refuse(element, "call without a declaration")
    if name == "pick" and len(actuals) == PICK_ARGUMENTS:
        return _choose(*(render(ctx, node) for node in actuals))
    if name in CLOG2 and len(actuals) == 1:
        arg = render(ctx, actuals[0])
        if arg.number is not None:
            number = (arg.number - 1).bit_length()
            return Value(str(number), number)
        return Value(f"$clog2({arg.text})", None)
    return _expand(ctx, element, decl)


def _binary(ctx: Context, element: Element) -> Value:
    """Render an arithmetic operator with two operands."""
    sign, func = BINARY[element.get("kind", "")]
    left = render(ctx, _operand(element, "left"))
    right = render(ctx, _operand(element, "right"))
    if left.number is not None and right.number is not None:
        number = func(left.number, right.number)
        return Value(str(number), number)
    return Value(f"({left.text} {sign} {right.text})", None)


def _unary(ctx: Context, element: Element) -> Value:
    """Render a sign."""
    sign, func = UNARY[element.get("kind", "")]
    inner = render(ctx, _operand(element, "operand"))
    if inner.number is not None:
        number = func(inner.number)
        return Value(str(number), number)
    return Value(f"({sign}{inner.text})", None)


def _logic(ctx: Context, element: Element) -> Value:
    """Render a boolean or relational operator."""
    sign, func = LOGIC[element.get("kind", "")]
    left = render(ctx, _operand(element, "left"))
    right = render(ctx, _operand(element, "right"))
    if left.number is not None and right.number is not None:
        number = func(left.number, right.number)
        return Value(str(number), number)
    return Value(f"({left.text} {sign} {right.text})", None)


def _operand(element: Element, tag: str) -> Element:
    """Take the operand child of an operator."""
    node = element.find(tag)
    if node is None:
        raise refuse(element, f"operator without {tag}")
    return node


def _paren(ctx: Context, element: Element) -> Value:
    """Render a parenthesis expression as its content."""
    return render(ctx, _operand(element, "expression"))


def _render_kind(ctx: Context, element: Element, kind: str) -> Value | None:
    """Render the kinds that have a handler of their own, else None."""
    if kind == "integer_literal":
        return _literal(element)
    if kind == "enumeration_literal":
        return _enumeration(element)
    handler = _HANDLERS.get(kind)
    return None if handler is None else handler(ctx, element)


_HANDLERS: dict[str, Callable[[Context, Element], Value]] = {
    "simple_name": _name,
    "selected_name": _name,
    "parenthesis_expression": _paren,
    "function_call": _call,
    **dict.fromkeys(BINARY, _binary),
    **dict.fromkeys(UNARY, _unary),
    **dict.fromkeys(LOGIC, _logic),
}


def render(ctx: Context, element: Element) -> Value:
    """Render an expression of the syntax tree.

    Parameters
    ----------
    ctx : Context
        The index of the tree and the entity.
    element : Element
        The expression node.

    Returns
    -------
    Value
        The SystemVerilog text and the value when it is constant.

    Raises
    ------
    ExtractError
        If the expression uses a construct with no SystemVerilog form.
    """
    kind = element.get("kind", "")
    rendered = _render_kind(ctx, element, kind)
    if rendered is None:
        raise refuse(element, f"expression of kind {kind} has no form")
    return rendered
