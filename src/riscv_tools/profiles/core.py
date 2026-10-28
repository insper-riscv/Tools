r"""Expand a profile specification into every valid combination of extensions.

A core profile is a set of optional extensions on top of a base ISA. Writing the list by
hand lets an impossible combination slip in (M together with Zmmul, a core with neither
Zicsr nor Zicclsm), so a specification states the extensions and the rules between them,
and this module expands it into the combinations that obey every rule.

```yaml
base: rv32i                       # name of a profile with no extension
extensions:                       # the order is the order of the name's tokens
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}      # rv32i + m = rv32im
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:               # at most one extension of each group
  - [M, Zmmul]
requires_any:                     # at least one extension of each group
  - [Zicsr, Zicclsm]
```

A profile is named after the extensions it has: `base_letter` goes into the base name
(`rv32i` + `m` = `rv32im`) and every other extension adds `_<name in lowercase>`. An
extension with an `absent_token` is on by default: its name stays out of the name while
it is present, and the token is added when it is missing.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True)
class Extension:
    """One optional extension and how it shows in the core and in the name."""

    name: str
    generic: str
    base_letter: str | None = None
    absent_token: str | None = None


@dataclass(frozen=True)
class Spec:
    """The extensions of a core and the rules between them."""

    base: str
    extensions: tuple[Extension, ...]
    mutually_exclusive: tuple[tuple[str, ...], ...]
    requires_any: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Profile:
    """One valid combination of extensions."""

    name: str
    extensions: tuple[str, ...]
    generics: Mapping[str, bool]


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
            raise ValueError(f"{key}: unknown extension(s) {', '.join(unknown)}")
        groups.append(names)
    return tuple(groups)


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
        If the file lacks the base name or an extension, repeats a name, or a rule
        mentions an extension that is not listed.
    """
    loaded: Any = yaml.safe_load(path.read_text())
    raw = cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else {}
    if "base" not in raw or not raw.get("extensions"):
        raise ValueError(f"{path}: needs `base` and a non-empty `extensions` list")
    extensions = tuple(
        Extension(
            name=str(e["name"]),
            generic=str(e["generic"]),
            base_letter=_optional(e, "base_letter"),
            absent_token=_optional(e, "absent_token"),
        )
        for e in cast("list[dict[str, Any]]", raw["extensions"])
    )
    names = [e.name for e in extensions]
    if len(set(names)) != len(names):
        raise ValueError(f"{path}: an extension name is repeated")
    known = set(names)
    return Spec(
        base=str(raw["base"]),
        extensions=extensions,
        mutually_exclusive=_groups(raw, "mutually_exclusive", known),
        requires_any=_groups(raw, "requires_any", known),
    )


def _valid(present: frozenset[str], spec: Spec) -> bool:
    if any(len(present.intersection(group)) > 1 for group in spec.mutually_exclusive):
        return False
    return all(present.intersection(group) for group in spec.requires_any)


def _name(present: frozenset[str], spec: Spec) -> str:
    base = spec.base + "".join(
        e.base_letter for e in spec.extensions if e.name in present and e.base_letter
    )
    tokens: list[str] = []
    for e in spec.extensions:
        if e.name in present and not e.base_letter and not e.absent_token:
            tokens.append(e.name.lower())
        elif e.name not in present and e.absent_token:
            tokens.append(e.absent_token)
    return "_".join([base, *tokens])


def expand(spec: Spec) -> list[Profile]:
    """List every combination of the extensions that obeys the rules.

    Parameters
    ----------
    spec : Spec
        The extensions and rules.

    Returns
    -------
    list[Profile]
        The valid profiles, ordered by how many extensions they have and then by the
        order of the extensions in the specification.
    """
    names: Sequence[str] = [e.name for e in spec.extensions]
    profiles: list[Profile] = []
    for flags in itertools.product([False, True], repeat=len(names)):
        present = frozenset(n for n, on in zip(names, flags, strict=True) if on)
        if not _valid(present, spec):
            continue
        profiles.append(
            Profile(
                name=_name(present, spec),
                extensions=tuple(n for n in names if n in present),
                generics={e.generic: e.name in present for e in spec.extensions},
            )
        )
    return sorted(
        profiles,
        key=lambda p: (len(p.extensions), tuple(names.index(n) for n in p.extensions)),
    )
