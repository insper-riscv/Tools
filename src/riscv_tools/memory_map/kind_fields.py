"""The fields of the external kinds that become generics.

Each field of an entry of `peripherals` is the generic of an entity of
`Peripherals` with the same name. The registry of kinds
(`riscv_tools.memory_map.kinds`) lists them with the helpers below, and
the entry reader and the generated top read the types from here.

The types are the ones a generic can take.

- `int` is a natural or positive number (`minimum`, and `maximum` when
  not zero, bound it).
- `bool` is a boolean.
- `choice` is one of `choices`, written as a VHDL string.
- `hex` is a string of hexadecimal digits, a multiple of four of them
  (one register and one value for each four), written as a VHDL string.
- `addr7` is a 7-bit I2C address, written as a bit string.
"""

from dataclasses import dataclass

TYPES = ("int", "bool", "choice", "hex", "addr7")
ADDR7_MAX = 127
HEX_GROUP = 4


@dataclass(frozen=True)
class FieldSpec:
    """A field of an entry of `peripherals`, written as a generic.

    Parameters
    ----------
    name : str
        The key of the entry.
    type : str
        One of `TYPES`.
    generic : str
        The generic of the entity that receives the value.
    group : str
        The part of the entity the field belongs to (`mac`, `mdio`),
        empty for a field with no part.
    minimum : int
        The least value of an `int` (1 for a `positive` generic).
    maximum : int
        The greatest value of an `int`; zero for no limit.
    choices : tuple of str
        The values of a `choice`.
    only : tuple of str
        The entities (keys of the variants) that have the generic;
        empty when every entity of the kind has it.
    """

    name: str
    type: str
    generic: str
    group: str = ""
    minimum: int = 0
    maximum: int = 0
    choices: tuple[str, ...] = ()
    only: tuple[str, ...] = ()


def ints(
    names: str, minimum: int = 0, only: tuple[str, ...] = ()
) -> tuple[FieldSpec, ...]:
    """Write integer fields whose generic has the name of the field.

    Parameters
    ----------
    names : str
        The names, separated by spaces.
    minimum : int
        The least value (1 for a `positive` generic).
    only : tuple of str
        The entities that have the generics.

    Returns
    -------
    tuple of FieldSpec
        One field for each name.
    """
    return tuple(
        FieldSpec(n, "int", n, minimum=minimum, only=only)
        for n in names.split()
    )


def ranged(name: str, minimum: int, maximum: int) -> FieldSpec:
    """Write an integer field with both limits.

    Parameters
    ----------
    name : str
        The field and the generic.
    minimum : int
        The least value.
    maximum : int
        The greatest value.

    Returns
    -------
    FieldSpec
        The field.
    """
    return FieldSpec(name, "int", name, minimum=minimum, maximum=maximum)


def bools(names: str, only: tuple[str, ...] = ()) -> tuple[FieldSpec, ...]:
    """Write boolean fields whose generic has the name of the field.

    Parameters
    ----------
    names : str
        The names, separated by spaces.
    only : tuple of str
        The entities that have the generics.

    Returns
    -------
    tuple of FieldSpec
        One field for each name.
    """
    return tuple(FieldSpec(n, "bool", n, only=only) for n in names.split())
