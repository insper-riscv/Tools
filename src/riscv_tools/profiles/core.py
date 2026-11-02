r"""Expand a profile specification into valid extension combinations.

A core profile is a set of optional extensions on top of a base ISA. A
specification states the extensions and the rules between them (for
example M excludes Zmmul), and this module expands it into the
combinations that obey every rule.

```yaml
bases:                       # name of the profile with no extension
  - {name: rv32i, generics: {num_regs: 32}}
  - {name: rv32e, generics: {num_regs: 16}}
extensions:                  # order = order of the tokens in the name
  - {name: Zicsr,  generic: has_zicsr}
  - {name: Zicntr, generic: has_zicntr, implies: [has_zicsr]}
  - {name: M,      generic: has_m, base_letter: m}  # rv32i+m = rv32im
mutually_exclusive:          # at most one extension of each group
  - [M, Zmmul]
requires_any:                # at least one of each group (optional)
  - [Zicsr, Zicclsm]
```

A specification with a single base may write `base: rv32i` instead of
`bases`. Every base is combined with every valid set of extensions, and
the generics of the base go into the profile before those of the
extensions.

A profile is named after its extensions: `base_letter` goes into the
base name and every other extension adds `_<name in lowercase>`. An
extension with `implies` also turns on the listed generics, so its name
never cites the implied extension. An extension with `absent_token` is
on by default: its name stays out while present, and the token is added
when it is missing.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True)
class Extension:
    """One optional extension, as shown in the core and in the name."""

    name: str
    generic: str
    base_letter: str | None = None
    absent_token: str | None = None
    implies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Base:
    """One base ISA, with the generics that select it in the core."""

    name: str
    generics: Mapping[str, bool | int] = field(
        default_factory=dict[str, bool | int]
    )


@dataclass(frozen=True)
class Spec:
    """The bases and extensions of a core and the rules between them."""

    bases: tuple[Base, ...]
    extensions: tuple[Extension, ...]
    mutually_exclusive: tuple[tuple[str, ...], ...]
    requires_any: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Profile:
    """One valid combination of extensions."""

    name: str
    extensions: tuple[str, ...]
    generics: Mapping[str, bool | int]
    base: str = ""


def _optional(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    return None if value is None else str(value)


def _groups(
    raw: dict[str, Any], key: str, known: set[str]
) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    for group in cast("list[list[Any]]", raw.get(key) or []):
        names = tuple(str(n) for n in group)
        unknown = [n for n in names if n not in known]
        if unknown:
            raise ValueError(
                f"{key}: unknown extension(s) {', '.join(unknown)}"
            )
        groups.append(names)
    return tuple(groups)


def _bases(path: Path, raw: dict[str, Any]) -> tuple[Base, ...]:
    """Read the `base` or the `bases` entry of a specification."""
    if "base" in raw and "bases" not in raw:
        return (Base(name=str(raw["base"])),)
    entries = cast("list[dict[str, Any]]", raw.get("bases") or [])
    if not entries or "base" in raw:
        raise ValueError(
            f"{path}: needs either `base` or a non-empty `bases` list"
        )
    bases = tuple(
        Base(
            name=str(e["name"]),
            generics=cast("dict[str, bool | int]", e.get("generics") or {}),
        )
        for e in entries
    )
    if len({b.name for b in bases}) != len(bases):
        raise ValueError(f"{path}: a base name is repeated")
    return bases


def load_spec(path: Path) -> Spec:
    """Read a profile specification from a YAML file.

    Parameters
    ----------
    path : Path
        The YAML file.

    Returns
    -------
    Spec
        The extensions and rules of the file.

    Raises
    ------
    ValueError
        If the file lacks the base or an extension, repeats a name, or a
        rule mentions an extension that is not listed.
    """
    loaded: Any = yaml.safe_load(path.read_text())
    raw: dict[str, Any] = {}
    if isinstance(loaded, dict):
        raw = cast(dict[str, Any], loaded)
    if not raw.get("extensions"):
        raise ValueError(f"{path}: needs a non-empty `extensions` list")
    bases = _bases(path, raw)
    extensions = tuple(
        Extension(
            name=str(e["name"]),
            generic=str(e["generic"]),
            base_letter=_optional(e, "base_letter"),
            absent_token=_optional(e, "absent_token"),
            implies=tuple(
                str(g) for g in cast("list[object]", e.get("implies") or [])
            ),
        )
        for e in cast(list[dict[str, Any]], raw["extensions"])
    )
    names = [e.name for e in extensions]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: an extension name is repeated")
    known = set(names)
    return Spec(
        bases=bases,
        extensions=extensions,
        mutually_exclusive=_groups(raw, "mutually_exclusive", known),
        requires_any=_groups(raw, "requires_any", known),
    )


def _generics(
    present: frozenset[str], base: Base, spec: Spec
) -> dict[str, bool | int]:
    """Give the generics of the base and of the extensions on."""
    generics: dict[str, bool | int] = dict(base.generics)
    generics.update({e.generic: e.name in present for e in spec.extensions})
    for e in spec.extensions:
        if e.name in present:
            for implied in e.implies:
                generics[implied] = True
    return generics


def _valid(present: frozenset[str], spec: Spec) -> bool:
    if any(
        len(present.intersection(group)) > 1
        for group in spec.mutually_exclusive
    ):
        return False
    return all(present.intersection(group) for group in spec.requires_any)


def _name(present: frozenset[str], base_name: str, spec: Spec) -> str:
    base = base_name + "".join(
        e.base_letter
        for e in spec.extensions
        if e.name in present and e.base_letter
    )
    tokens: list[str] = []
    for e in spec.extensions:
        if e.name in present and not e.base_letter and not e.absent_token:
            tokens.append(e.name.lower())
        elif e.name not in present and e.absent_token:
            tokens.append(e.absent_token)
    return "_".join([base, *tokens])


def _of_base(base: Base, names: Sequence[str], spec: Spec) -> list[Profile]:
    """List the valid combinations of the extensions over one base."""
    profiles: list[Profile] = []
    for flags in itertools.product([False, True], repeat=len(names)):
        present = frozenset(
            n for n, on in zip(names, flags, strict=True) if on
        )
        if _valid(present, spec):
            profiles.append(
                Profile(
                    name=_name(present, base.name, spec),
                    extensions=tuple(n for n in names if n in present),
                    generics=_generics(present, base, spec),
                    base=base.name,
                )
            )
    return profiles


def expand(spec: Spec) -> list[Profile]:
    """List every combination of the extensions that obeys the rules.

    Parameters
    ----------
    spec : Spec
        The bases, extensions and rules.

    Returns
    -------
    list[Profile]
        The valid profiles, ordered by base (in the order of the
        specification), then by how many extensions they have and then
        by the order of the extensions in the specification.
    """
    names: Sequence[str] = [e.name for e in spec.extensions]
    profiles = [p for b in spec.bases for p in _of_base(b, names, spec)]
    order = [b.name for b in spec.bases]
    return sorted(
        profiles,
        key=lambda p: (
            order.index(p.base),
            len(p.extensions),
            tuple(names.index(n) for n in p.extensions),
        ),
    )
