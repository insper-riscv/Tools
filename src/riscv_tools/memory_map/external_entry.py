"""Read one entry of `peripherals` whose `kind` is an external kind.

Apart from `external` so that `layout`, which `core` loads, can read the
entries without importing `core` back.
"""

import re
from typing import Any

from riscv_tools.memory_map import kinds
from riscv_tools.memory_map.kind_fields import ADDR7_MAX, HEX_GROUP, FieldSpec

NEEDS = ("required", "optional")
_COMMON = {"kind", "base", "size", "instance", "need"}
_HEX = re.compile(r"[0-9A-Fa-f]*")


def _is_int(value: Any) -> bool:
    """Tell whether a value is an integer and not a boolean."""
    return isinstance(value, int) and not isinstance(value, bool)


def _int_error(spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with an `int` value, if anything."""
    if not _is_int(value):
        return "must be of type int"
    if value < spec.minimum:
        return f"must be at least {spec.minimum}"
    if spec.maximum and value > spec.maximum:
        return f"must be at most {spec.maximum}"
    return ""


def _bool_error(_spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with a `bool` value, if anything."""
    return "" if isinstance(value, bool) else "must be of type bool"


def _addr7_error(_spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with an `addr7` value, if anything."""
    if _is_int(value) and 0 <= value <= ADDR7_MAX:
        return ""
    return f"must be an integer from 0 to {ADDR7_MAX}"


def _choice_error(spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with a `choice` value, if anything."""
    if isinstance(value, str) and value in spec.choices:
        return ""
    return f"must be one of {list(spec.choices)}"


def _hex_error(_spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with a `hex` value, if anything."""
    ok = isinstance(value, str) and _HEX.fullmatch(value)
    if ok and len(value) % HEX_GROUP == 0:
        return ""
    return f"must be hexadecimal, {HEX_GROUP} digits per entry"


_CHECKS = {
    "int": _int_error,
    "bool": _bool_error,
    "addr7": _addr7_error,
    "choice": _choice_error,
    "hex": _hex_error,
}


def _value_error(where: str, spec: FieldSpec, value: Any) -> str:
    """Say what is wrong with the value of a field, if anything.

    Parameters
    ----------
    where : str
        The path of the entry.
    spec : FieldSpec
        The field.
    value : Any
        The value written.

    Returns
    -------
    str
        The message; empty when the value fits the type of the field.
    """
    text = _CHECKS[spec.type](spec, value)
    return f"{where}.{spec.name} {text}" if text else ""


def _check_keys(
    where: str, kind: kinds.ExternalKind, value: dict[str, Any]
) -> None:
    """Check the keys of an entry: no unknown one, `base` and `need`."""
    allowed = _COMMON | {f.name for f in kind.fields}
    if kind.variant_field:
        allowed.add(kind.variant_field)
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError(f"{where} has unknown keys {extra}")
    if "base" not in value:
        raise ValueError(f"{where}.base is required")
    if value.get("need", "required") not in NEEDS:
        raise ValueError(f"{where}.need must be one of {list(NEEDS)}")


def _check_fields(
    where: str, kind: kinds.ExternalKind, value: dict[str, Any]
) -> None:
    """Check the fields the kind adds: their type, and their entity."""
    chosen = str(value.get(kind.variant_field, kind.default_variant))
    for spec in kind.fields:
        if spec.name not in value:
            continue
        if spec.only and chosen in kind.variants and chosen not in spec.only:
            raise ValueError(
                f"{where}.{spec.name} does not apply to "
                f"{kind.variant_field} {chosen}, only to {list(spec.only)}"
            )
        text = _value_error(where, spec, value[spec.name])
        if text:
            raise ValueError(text)


def entry(name: str, value: dict[str, Any]) -> dict[str, Any]:
    """Read one entry of an external kind.

    Parameters
    ----------
    name : str
        The key of the entry.
    value : dict of {str: Any}
        The entry.

    Returns
    -------
    dict of {str: Any}
        The entry with its `name`; `size` is the registers of the
        entity when it is not written.

    Raises
    ------
    ValueError
        If the entry has a key the kind does not know, lacks `base`,
        or a field has the wrong type.
    """
    where = f"peripherals.{name}"
    kind = kinds.EXTERNAL[str(value["kind"])]
    _check_keys(where, kind, value)
    _check_fields(where, kind, value)
    found = {"name": name, **value}
    if "size" not in found:
        variant = kind.variant(found)
        found["size"] = variant.window if variant else 16
    return found
