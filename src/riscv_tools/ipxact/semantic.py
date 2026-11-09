"""Check the semantic consistency rules of IEEE Std 1685-2022.

The schema cannot say that an expression names an existing parameter
or that a value fits its type. This module checks, on one
`ipxact:component` document, the rules of annexes B and C that a single
document can break. Each message begins with the number of the rule.

| Rule | Clause | What is checked |
| :--- | :--- | :--- |
| SCR 1.10 | B.2.1 | the document element is a legal type |
| SCR 5.2 | C.6.2 | `parameterId` on a user or generated parameter |
| SCR 5.13 | C.7 | a value is inside `minimum` and `maximum` |
| SCR 5.14 | 6.15.2.2 | a module parameter stays in its instantiation |
| SCR 5.16 | C.21 | a value resolves to the type of the parameter |
| SCR 5.17 | Annex E | an expression is well formed |
| SCR 5.18 | C.9.2 | an identifier of an expression is a `parameterId` |
| SCR 5.19 | B.2.5 | an expression does not refer to itself |
| SCR 6.26 | 6.15.1.2 | no view means only phantom ports |
| C.29.2 | C.29 | a `viewRef` names a view, once per `wireTypeDefs` |
| C.7.11 | C.7.11 | a vector limit is a non-negative integer |
"""

from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from riscv_tools.ipxact.component import NAMESPACE
from riscv_tools.ipxact.sv_expr import (
    ExpressionError,
    evaluate,
    identifiers,
)

LEGAL_ROOTS = frozenset(
    {
        "abstractor",
        "abstractionDefinition",
        "busDefinition",
        "component",
        "design",
        "designConfiguration",
        "generatorChain",
        "typeDefinitions",
        "catalog",
    }
)
LIMITS = ("left", "right")


def _tag(name: str) -> str:
    """Qualify a tag with the IP-XACT namespace."""
    return f"{{{NAMESPACE}}}{name}"


def _text(node: Element | None, tag: str) -> str:
    """Read the text of a child, empty when absent."""
    child = None if node is None else node.find(_tag(tag))
    return "" if child is None else (child.text or "").strip()


class UnresolvedError(ExpressionError):
    """A parameter the user sets, so it has no value to evaluate."""


class _Parameters:
    """The parameters of a component and the value of each one."""

    def __init__(self, root: Element) -> None:
        """Index the parameters by `parameterId`.

        Parameters
        ----------
        root : Element
            The component element.
        """
        self.nodes: dict[str, Element] = {}
        self.module_ids: set[str] = set()
        self.problems: list[str] = []
        self.cache: dict[str, int] = {}
        self.stack: list[str] = []
        for tag in ("parameter", "moduleParameter"):
            for node in root.iter(_tag(tag)):
                self._add(node, tag == "moduleParameter")

    def _add(self, node: Element, module: bool) -> None:
        """Index a parameter and report a missing `parameterId`."""
        identifier = node.get("parameterId", "")
        if node.get("resolve", "immediate") in ("user", "generated") and (
            not identifier
        ):
            self.problems.append(
                f"SCR 5.2: parameter {_text(node, 'name')} resolves to"
                " user or generated and has no parameterId"
            )
        if identifier:
            self.nodes[identifier] = node
            if module:
                self.module_ids.add(identifier)

    def value_of(self, identifier: str) -> int:
        """Evaluate a parameter, following the ones it names.

        Parameters
        ----------
        identifier : str
            A `parameterId`.

        Returns
        -------
        int
            The value.

        Raises
        ------
        ExpressionError
            If the name does not exist, is circular or has no value.
        """
        if identifier in self.cache:
            return self.cache[identifier]
        if identifier not in self.nodes:
            raise ExpressionError(
                f"SCR 5.18: {identifier!r} is not a parameterId"
            )
        if identifier in self.stack:
            chain = " -> ".join([*self.stack, identifier])
            raise ExpressionError(f"SCR 5.19: {chain}")
        text = _text(self.nodes[identifier], "value")
        if not text:
            raise UnresolvedError(identifier)
        self.stack.append(identifier)
        try:
            value = evaluate(text, self.value_of)
        finally:
            self.stack.pop()
        self.cache[identifier] = value
        return value


def _expression_problems(
    where: str, text: str, params: _Parameters
) -> list[str]:
    """Check the syntax, the names and the value of an expression."""
    try:
        evaluate(text, params.value_of)
    except UnresolvedError:
        return []
    except ExpressionError as error:
        message = str(error)
        rule = "" if message.startswith("SCR") else "SCR 5.17: "
        return [f"{rule}{where}: {message}"]
    return []


def _bound_problems(node: Element, name: str, number: int) -> list[str]:
    """Check a value against the `minimum` and `maximum` of its node."""
    found: list[str] = []
    low, high = node.get("minimum"), node.get("maximum")
    if low is not None and number < int(low):
        found.append(f"SCR 5.13: parameter {name}: {number} < minimum {low}")
    if high is not None and number > int(high):
        found.append(f"SCR 5.13: parameter {name}: {number} > maximum {high}")
    return found


def _parameter_problems(node: Element, params: _Parameters) -> list[str]:
    """Check that a parameter value fits its type and bounds."""
    name, text = _text(node, "name"), _text(node, "value")
    kind = node.get("type", "string")
    if not text or kind == "string":
        return []
    found = _expression_problems(f"parameter {name}", text, params)
    if found:
        return found
    try:
        number = evaluate(text, params.value_of)
    except ExpressionError:
        return [f"SCR 5.16: parameter {name}: {text!r} is not of type {kind}"]
    return _bound_problems(node, name, number)


def _vector_problems(root: Element, params: _Parameters) -> list[str]:
    """Check the limits of every vector."""
    found: list[str] = []
    for node in root.iter():
        short = node.tag.split("}")[-1]
        if short not in LIMITS or node.tag != _tag(short):
            continue
        text = (node.text or "").strip()
        where = f"{short} limit of a vector"
        problems = _expression_problems(where, text, params)
        found.extend(problems)
        if not problems and _negative(text, params):
            found.append(f"C.7.11: {where}: {text!r} is negative")
    return found


def _negative(text: str, params: _Parameters) -> bool:
    """Tell whether an expression evaluates below zero."""
    try:
        return evaluate(text, params.value_of) < 0
    except ExpressionError:
        return False


def _outside_use(root: Element, params: _Parameters) -> list[str]:
    """Check that no expression names a module parameter outside."""
    inside = {
        id(node)
        for parent in root.iter(_tag("componentInstantiation"))
        for node in parent.iter()
    }
    found: list[str] = []
    for node in root.iter():
        if id(node) not in inside:
            found.extend(
                f"SCR 5.14: {name!r} is a module parameter used outside"
                " its instantiation"
                for name in sorted(_names(node) & params.module_ids)
            )
    return found


def _names(node: Element) -> set[str]:
    """List the identifiers in the text of an element, if it is one."""
    try:
        return set(identifiers(node.text or ""))
    except ExpressionError:
        return set()


def _view_names(root: Element) -> list[str]:
    """List the names of the views of the component."""
    return [_text(view, "name") for view in root.iter(_tag("view"))]


def _port_problems(root: Element) -> list[str]:
    """Check that a component without views has only phantom ports."""
    if _view_names(root):
        return []
    return [
        f"SCR 6.26: port {_text(port, 'name')} of a component without"
        " views is not phantom"
        for port in root.iter(_tag("port"))
        if _text(port.find(_tag("wire")), "direction") != "phantom"
    ]


def _view_reference_problems(root: Element) -> list[str]:
    """Check that a `viewRef` names a view, once in each list."""
    views = _view_names(root)
    found: list[str] = []
    for defs in root.iter(_tag("wireTypeDefs")):
        refs = [(ref.text or "").strip() for ref in defs.iter(_tag("viewRef"))]
        found.extend(
            f"C.29.2: viewRef {ref!r} names no view"
            for ref in refs
            if ref not in views
        )
        found.extend(
            f"C.29.2: view {ref!r} is referenced more than once"
            for ref, count in Counter(refs).items()
            if count > 1
        )
    return found


def check_component(path: Path) -> list[str]:
    """Check the semantic rules a single component document can break.

    Parameters
    ----------
    path : Path
        The `ipxact:component` file.

    Returns
    -------
    list of str
        One line for each broken rule, naming the rule.
    """
    root = ElementTree.parse(path).getroot()
    if root is None:
        return [f"SCR 1.10: {path.name}: no document element"]
    name = root.tag.split("}")[-1]
    if name not in LEGAL_ROOTS:
        return [f"SCR 1.10: {path.name}: {name} is not a document type"]
    params = _Parameters(root)
    found = list(params.problems)
    for node in root.iter(_tag("parameter")):
        found.extend(_parameter_problems(node, params))
    found.extend(_vector_problems(root, params))
    found.extend(_outside_use(root, params))
    found.extend(_port_problems(root))
    found.extend(_view_reference_problems(root))
    return [f"{path.name}: {line}" for line in dict.fromkeys(found)]
