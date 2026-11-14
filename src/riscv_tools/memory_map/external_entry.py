"""Read one entry of `peripherals` whose `kind` is an external kind.

Apart from `external` so that `layout`, which `core` loads, can read the
entries without importing `core` back.
"""

from typing import Any

from riscv_tools.memory_map import kinds

NEEDS = ("required", "optional")
_COMMON = {"kind", "base", "size", "instance", "need"}


def _value_error(where: str, spec: kinds.FieldSpec, value: Any) -> str:
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
        The message; empty when the value has the type of the field.
    """
    if spec.type == "bool" and isinstance(value, bool):
        return ""
    if (
        spec.type == "int"
        and isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return ""
    return f"{where}.{spec.name} must be of type {spec.type}"


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
    """Check the type of the fields the kind adds."""
    for spec in kind.fields:
        text = (
            _value_error(where, spec, value[spec.name])
            if spec.name in value
            else ""
        )
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
