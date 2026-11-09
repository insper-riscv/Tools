"""The internal model of a VHDL entity, from which IP-XACT is built.

The model holds what `ipxact:component` needs and nothing else: the
generics as parameters, the ports with their vector limits as
expressions of those parameters, and the documentation comments.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Generic:
    """A generic of an entity, which becomes a component parameter.

    Parameters
    ----------
    name : str
        The generic name as written in the VHDL.
    vhdl_type : str
        The name of its VHDL type (`natural`, `boolean`, ...).
    default : str or None
        The default value as an expression of the other generics; None
        when the VHDL gives none.
    description : str
        The comment above the declaration.
    minimum : int or None
        The lower bound of the subtype, when it has one.
    maximum : int or None
        The upper bound of the subtype, when it has one.
    vectors : tuple of (str, str)
        The (left, right) limits when the generic is a bit vector.
    """

    name: str
    vhdl_type: str
    default: str | None
    description: str
    minimum: int | None = None
    maximum: int | None = None
    vectors: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Port:
    """A port of an entity, which becomes a component wire port.

    Parameters
    ----------
    name : str
        The port name as written in the VHDL.
    direction : str
        `in`, `out` or `inout`.
    type_name : str
        The VHDL type mark (`std_logic`, `std_logic_vector`, ...).
    vectors : tuple of (str, str)
        The (left, right) limits of each array dimension as expressions
        of the generics; empty for a scalar.
    description : str
        The comment above the declaration.
    type_definition : str
        The package that declares the type (`ieee.std_logic_1164.all`).
    """

    name: str
    direction: str
    type_name: str
    vectors: tuple[tuple[str, str], ...]
    description: str
    type_definition: str = ""


@dataclass(frozen=True)
class Entity:
    """An entity read from the VHDL.

    Parameters
    ----------
    name : str
        The entity name.
    source : str
        The file that declares it, relative to the repository root.
    generics : tuple of Generic
        The generics in declaration order.
    ports : tuple of Port
        The ports in declaration order.
    description : str
        The summary line of the header of the file.
    """

    name: str
    source: str
    generics: tuple[Generic, ...]
    ports: tuple[Port, ...]
    description: str


class ExtractError(ValueError):
    """A VHDL construct the extraction cannot turn into IP-XACT."""
