"""Read the entities of VHDL files from the syntax tree GHDL exports.

`ghdl --file-to-xml` writes the abstract syntax tree of the analyzed
files, with the names already resolved to their declarations. The
files it depends on have to be analyzed before, in the order the
`provides` manifest lists them.
"""

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from riscv_tools.ipxact.expression import (
    Context,
    Index,
    refuse,
    render,
    target,
)
from riscv_tools.ipxact.model import Entity, ExtractError, Generic, Port

STD = "--std=08"
DIRECTIONS = {"in": "in", "out": "out", "inout": "inout"}
WIRE_TYPES = frozenset(
    {
        "std_logic",
        "std_ulogic",
        "std_logic_vector",
        "std_ulogic_vector",
        "unsigned",
        "signed",
        "bit",
        "bit_vector",
    }
)
GENERIC_TYPES = frozenset(
    {"natural", "integer", "positive", "boolean", "string"}
)
IMPLIED_MINIMUM = {"natural": 0, "positive": 1}
GENERIC_BIT_TYPES = frozenset({"std_logic", "std_logic_vector"})
PACKAGE_LIBRARIES = {
    "std_logic_1164": "ieee",
    "numeric_std": "ieee",
    "standard": "std",
}


def analyze(files: Sequence[Path], workdir: Path) -> None:
    """Analyze files in order into a GHDL library.

    Parameters
    ----------
    files : sequence of Path
        The files, dependencies first.
    workdir : Path
        The folder that receives the library.

    Raises
    ------
    ExtractError
        If GHDL rejects a file; a warning counts as a rejection.
    """
    command = ["ghdl", "-a", STD, f"--workdir={workdir}", "-Werror"]
    command.extend(str(path) for path in files)
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise ExtractError(f"ghdl -a failed: {done.stderr.strip()}")


def dump(files: Sequence[Path], workdir: Path) -> Element:
    """Export the syntax tree of analyzed files.

    Parameters
    ----------
    files : sequence of Path
        The files whose units are wanted.
    workdir : Path
        The library the files were analyzed into.

    Returns
    -------
    Element
        The root of the exported tree.

    Raises
    ------
    ExtractError
        If GHDL fails to export.
    """
    command = ["ghdl", "--file-to-xml", STD, f"--workdir={workdir}"]
    command.extend(str(path) for path in files)
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise ExtractError(f"ghdl --file-to-xml failed: {done.stderr}")
    return ElementTree.fromstring(done.stdout)


def tree_index(root: Element) -> Index:
    """Index the elements of a tree by `id`, and bodies by declaration.

    Parameters
    ----------
    root : Element
        The tree `dump` returned.

    Returns
    -------
    dict of str to Element
        Each element that has an `id`; a function body is also under
        `body:<id of its declaration>`, because the declaration of a
        function of a package does not link to its body.
    """
    index: Index = {}
    for node in root.iter():
        if node.get("id"):
            index[node.get("id", "")] = node
        if node.get("kind") == "function_body":
            spec = node.find("subprogram_specification")
            if spec is not None:
                index[f"body:{spec.get('ref', '')}"] = node
    return index


def _comment_above(lines: list[str], line: int) -> str:
    """Join the comment lines right above a declaration."""
    found: list[str] = []
    cursor = line - 2
    while cursor >= 0 and lines[cursor].strip().startswith("--"):
        found.append(lines[cursor].strip().lstrip("-").strip())
        cursor -= 1
    return " ".join(reversed(found)).strip()


def _summary(lines: list[str]) -> str:
    """Take the first sentence line of the header comment."""
    for text in lines[:12]:
        body = text.strip().lstrip("-").strip()
        if body and set(body) != {"="}:
            return body
    return ""


def _limits(ctx: Context, constraint: Element) -> tuple[str, str]:
    """Render the two limits of a range constraint."""
    if constraint.get("kind") != "range_expression":
        raise refuse(constraint, "range given by an attribute or a name")
    left = constraint.find("left_limit_expr")
    right = constraint.find("right_limit_expr")
    if left is None or right is None:
        raise refuse(constraint, "range limits that are not expressions")
    return render(ctx, left).text, render(ctx, right).text


def _vectors(ctx: Context, array: Element) -> tuple[tuple[str, str], ...]:
    """Render the index constraints of an array and its elements."""
    found: list[tuple[str, str]] = []
    listing = array.find("index_constraint_list")
    for dimension in [] if listing is None else list(listing):
        constraint = dimension.find("range_constraint")
        if constraint is None:
            raise refuse(dimension, "index constraint without a range")
        found.append(_limits(ctx, constraint))
    element = array.find("array_element_constraint")
    if element is not None:
        found.extend(_vectors(ctx, element))
    return tuple(found)


def _is_wire_array(ctx: Context, decl: Element) -> bool:
    """Tell whether a type is an array of a wire type."""
    definition = decl.find("type_definition")
    if definition is None or definition.get("kind") != "array_type_definition":
        return False
    element = definition.find("element_subtype_indication")
    if element is None:
        return False
    inner = target(ctx, element, "named_entity")
    return inner is not None and (
        inner.get("identifier", "").lower() in WIRE_TYPES
    )


def package_of(ctx: Context, decl: Element) -> str:
    """Name the package that declares a type (`library.pkg.all`)."""
    parent = decl.find("parent")
    unit = None if parent is None else ctx.nodes.get(parent.get("ref", ""))
    if unit is None or unit.get("kind") != "package_declaration":
        return ""
    package = unit.get("identifier", "").lower()
    return f"{PACKAGE_LIBRARIES.get(package, 'work')}.{package}.all"


def resolve_type(
    ctx: Context, indication: Element
) -> tuple[str, tuple[tuple[str, str], ...], str]:
    """Resolve a subtype indication to a type mark and its vectors.

    Parameters
    ----------
    ctx : Context
        The index of the tree and the entity.
    indication : Element
        The subtype indication of a port or generic.

    Returns
    -------
    tuple of (str, tuple of (str, str), str)
        The type mark, the limits of each dimension and the package
        that declares the type.

    Raises
    ------
    ExtractError
        If the type is not one the translation covers.
    """
    kind = indication.get("kind", "")
    if kind in ("array_subtype_definition", "integer_subtype_definition"):
        mark = indication.find("subtype_type_mark")
        if mark is None:
            raise refuse(indication, f"{kind} without a type mark")
        name, inner, package = resolve_type(ctx, mark)
        return name, _vectors(ctx, indication) or inner, package
    decl = target(ctx, indication, "named_entity")
    if kind not in ("simple_name", "selected_name") or decl is None:
        raise refuse(indication, f"subtype indication of kind {kind}")
    return _named_type(ctx, indication, decl)


def _named_type(
    ctx: Context, indication: Element, decl: Element
) -> tuple[str, tuple[tuple[str, str], ...], str]:
    """Resolve a type or subtype name to its type mark."""
    name = decl.get("identifier", "").lower()
    known = name in WIRE_TYPES | GENERIC_TYPES or _is_wire_array(ctx, decl)
    if decl.get("kind") == "subtype_declaration" and not known:
        inner_node = decl.find("subtype_indication")
        if inner_node is None:
            raise refuse(indication, "subtype without an indication")
        return resolve_type(ctx, inner_node)
    if not known and decl.get("kind") == "type_declaration":
        raise refuse(indication, f"type {name} is not a wire or array type")
    return name, (), package_of(ctx, decl)


def _bounds(
    ctx: Context, indication: Element
) -> tuple[int | None, int | None]:
    """Read the numeric bounds of a constrained integer subtype."""
    if indication.get("kind") != "integer_subtype_definition":
        return None, None
    constraint = indication.find("range_constraint")
    if constraint is None:
        return None, None
    left, right = _limits(ctx, constraint)
    return _number(left), _number(right)


def _number(text: str) -> int | None:
    """Read a rendered limit as a number when it is one."""
    try:
        return int(text)
    except ValueError:
        return None


def _literal(lines: list[str], node: Element) -> tuple[str, str]:
    """Read the literal that follows the `:=` of a declaration.

    Returns
    -------
    tuple of (str, str)
        The base prefix (`x`, `b`, `o` or empty) and the digits.
    """
    row = int(node.get("line", "1")) - 1
    start = lines[row].find(":=")
    rest = lines[row][start + 2 :].lstrip() if start >= 0 else ""
    match = re.match(r'([xXbBoO]?)"([^"]*)"', rest)
    if match is None:
        raise refuse(node, "string literal not found in the source")
    return match.group(1).lower(), match.group(2)


def _source_text(lines: list[str], node: Element) -> str:
    """Read the text of a string generic."""
    return _literal(lines, node)[1]


def _sized(lines: list[str], node: Element) -> str:
    """Write a bit-string literal of the source as a sized literal."""
    base, digits = _literal(lines, node)
    bits = {"x": 4, "o": 3}.get(base, 1)
    letter = {"x": "h", "o": "o"}.get(base, "b")
    return f"{len(digits) * bits}'{letter}{digits}"


def _bits(node: Element, lines: list[str], width: int) -> str:
    """Render the default of a bit-vector generic as a sized literal."""
    kind = node.get("kind")
    if kind == "string_literal8":
        return _sized(lines, node)
    chain = node.find("association_choices_chain")
    only = None if chain is None else list(chain)
    if kind == "aggregate" and only is not None and len(only) == 1:
        fill = only[0].find("associated_expr")
        if (
            only[0].get("kind") == "choice_by_others"
            and fill is not None
            and fill.get("identifier") in ("'0'", "'1'")
        ):
            return f"{width}'b{fill.get('identifier', '')[1] * width}"
    raise refuse(node, "bit vector default that is not a literal or others")


def _default(
    ctx: Context, lines: list[str], node: Element, vectors: list[int]
) -> str:
    """Render the default value of a generic."""
    kind = node.get("kind")
    if kind == "string_literal8" and not vectors:
        return _source_text(lines, node)
    if kind == "character_literal":
        return f"1'b{node.get('identifier', '')[1]}"
    if vectors:
        return _bits(node, lines, vectors[0])
    return render(ctx, node).text


def _generic(ctx: Context, lines: list[str], node: Element) -> Generic:
    """Read one generic."""
    name = node.get("identifier", "")
    indication = node.find("subtype_indication")
    default = node.find("default_value")
    if indication is None:
        raise refuse(node, f"generic {name} without a type")
    type_name, vectors, _ = resolve_type(ctx, indication)
    if type_name not in GENERIC_TYPES | GENERIC_BIT_TYPES:
        raise refuse(node, f"generic {name} of type {type_name}")
    widths = [
        abs(left - right) + 1
        for left, right in ((_number(a), _number(b)) for a, b in vectors)
        if left is not None and right is not None
    ]
    minimum, maximum = _bounds(ctx, indication)
    minimum = IMPLIED_MINIMUM.get(type_name) if minimum is None else minimum
    text = None
    if default is not None:
        text = _default(ctx, lines, default, widths)
    line = int(node.get("line", "0"))
    return Generic(
        name,
        type_name,
        text,
        _comment_above(lines, line),
        minimum,
        maximum,
        vectors,
    )


def _port(ctx: Context, lines: list[str], node: Element) -> Port:
    """Read one port."""
    name = node.get("identifier", "")
    mode = node.get("mode", "")
    indication = node.find("subtype_indication")
    if mode not in DIRECTIONS or indication is None:
        raise refuse(node, f"port {name} of mode {mode}")
    type_name, vectors, package = resolve_type(ctx, indication)
    if type_name not in WIRE_TYPES and not package.startswith("work."):
        raise refuse(node, f"port {name} of type {type_name}")
    line = int(node.get("line", "0"))
    return Port(
        name,
        DIRECTIONS[mode],
        type_name,
        vectors,
        _comment_above(lines, line),
        package,
    )


class Read(NamedTuple):
    """The entities of an exported tree.

    Parameters
    ----------
    entities : list of Entity
        The entities that were translated.
    failures : dict of str to str
        For each entity that was not, the reason.
    """

    entities: list[Entity]
    failures: dict[str, str]


def _entity(
    ctx: Context, unit: Element, path: Path, repository: Path
) -> Entity:
    """Translate one entity declaration."""
    lines = path.read_text().splitlines()
    return Entity(
        unit.get("identifier", ""),
        path.relative_to(repository).as_posix(),
        tuple(
            _generic(ctx, lines, node)
            for node in unit.findall("generic_chain/el")
        ),
        tuple(
            _port(ctx, lines, node) for node in unit.findall("port_chain/el")
        ),
        _summary(lines),
    )


def entities(
    root: Element, repository: Path, wanted: dict[Path, Path]
) -> Read:
    """Read the entities of the wanted files from an exported tree.

    Parameters
    ----------
    root : Element
        The tree `dump` returned.
    repository : Path
        The repository root; the sources are named relative to it.
    wanted : dict of Path to Path
        The files whose entities are read, from the path GHDL analyzed
        to the original file (the same path unless it was reduced).

    Returns
    -------
    Read
        The entities, in the order of the tree, and the ones that use
        a construct the translation does not cover.
    """
    index = tree_index(root)
    found: list[Entity] = []
    failures: dict[str, str] = {}
    for unit in root.iter("library_unit"):
        analyzed = Path(unit.get("file", ""))
        if unit.get("kind") != "entity_declaration" or analyzed not in wanted:
            continue
        ctx = Context(index, unit.get("id", ""))
        try:
            found.append(_entity(ctx, unit, wanted[analyzed], repository))
        except ExtractError as error:
            failures[unit.get("identifier", "")] = str(error)
    return Read(found, failures)
