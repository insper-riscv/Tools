"""The `core` block of a platform and the profile it stands for.

The platform YAML does not name a profile. It describes the core in a
`core` block, and this module infers from it the profile of the
specification of the Core (`profiles/matrix.yaml`) and the extras.

```yaml
core:
  type: 32          # 32 or 64 (RV32 or RV64)
  base: I           # I or E (32 or 16 registers)
  extensions:       # or `extensions: []`
    - M
    - Zicsr
    - Zihintpause
    - Interrupts
```

The keys are lower case and the names of the extensions are not case
sensitive. The extensions of the specification (`M`, `Zmmul`, `Zicsr`,
`Zicntr`, `Zihpm`, `Zifencei`, `Zicclsm`, `Zimop` and `Zicond` in the
matrix of the Core) choose the profile, in the canonical order of its
name. The ones the specification does not list (`Zihintntl`,
`Zihintpause`, `Interrupts`, `Sscofpmf` and `AccessFaults`; also
`Zimop` and `Zicond` when the specification lacks them) are the extras,
which `--profile NAME` does not replace.

`Zicntr` and `Zihpm` imply `Zicsr` and `M` implies `Zmmul`, so listing
`Zicsr` beside `Zicntr` or `Zihpm` is accepted and the inferred name
does not cite it. An unknown or repeated extension, a combination that
the specification refuses (`M` with `Zmmul`) and a `type: 64` without
an `rv64` base in the specification are errors.

`profile:` and `extras:` are refused with the block that replaces them.
"""

from pathlib import Path
from typing import Any, cast

from riscv_tools import profiles

EXTRAS = (
    "Zihintntl",
    "Zihintpause",
    "Interrupts",
    "Sscofpmf",
    "AccessFaults",
)
OPTIONAL = ("Zimop", "Zicond")
KNOWN = (
    "M",
    "Zmmul",
    "Zicsr",
    "Zicntr",
    "Zihpm",
    "Zifencei",
    "Zicclsm",
    "Zimop",
    "Zicond",
)
IMPLYING_ZICSR = ("Zicntr", "Zihpm")
KEYS = ("type", "base", "extensions")
RV32 = 32
TYPES = (RV32, 64)


def _canonical(names: tuple[str, ...]) -> dict[str, str]:
    """Map the lower-case spelling of each name to its canonical one."""
    return {name.lower(): name for name in names}


def legacy_to_core(profile: str, extras: list[str]) -> dict[str, Any]:
    """Write the `core` block that a profile name and extras stand for.

    Parameters
    ----------
    profile : str
        The name of the profile, such as `rv32im_zicntr_zihpm`.
    extras : list of str
        The extras that went beside it.

    Returns
    -------
    dict of {str: Any}
        `type`, `base` and `extensions`: the `m` of the head of the
        name is `M`, each token is an extension (the first letters of a
        token after `rv32i` are not read) and the extras follow.

    Raises
    ------
    ValueError
        If the name does not start with `rv32i`, `rv32e`, `rv64i` or
        `rv64e`.
    """
    name = profile.lower()
    head, *tokens = name.split("_")
    if head[:4] not in ("rv32", "rv64") or head[4:5] not in ("i", "e"):
        raise ValueError(
            f"profile {profile!r} must start with rv32i, rv32e, rv64i or rv64e"
        )
    known = _canonical(KNOWN + EXTRAS)
    found = ["M"] if head[5:] == "m" else []
    found += [known.get(token, token.capitalize()) for token in tokens]
    return {
        "type": int(head[2:4]),
        "base": head[4].upper(),
        "extensions": found + [str(extra) for extra in extras],
    }


def _migration(data: dict[str, Any]) -> str:
    """Name the block that replaces `profile` and `extras`."""
    profile = str(data.get("profile", "rv32i"))
    extras = [str(e) for e in cast("list[Any]", data.get("extras") or [])]
    try:
        core = legacy_to_core(profile, extras)
    except ValueError:
        return "give a `core` block with `type`, `base` and `extensions`"
    listed = ", ".join(core["extensions"]) or "none"
    return (
        f"`profile: {profile}` becomes `core` with type {core['type']}, "
        f"base {core['base']} and extensions {listed}"
    )


def _read(core: Any, known: dict[str, str]) -> tuple[int, str, list[str]]:
    """Check the `core` block and read its three keys.

    Parameters
    ----------
    core : Any
        The value of `core`.
    known : dict of {str: str}
        The extensions that may be listed, by lower-case name.

    Returns
    -------
    tuple of (int, str, list of str)
        The width, the base letter (`i` or `e`) and the extensions in
        the canonical spelling, without the `Zicsr` that `Zicntr` or
        `Zihpm` already imply.

    Raises
    ------
    ValueError
        If the block is not well formed.
    """
    if not isinstance(core, dict):
        raise ValueError("core must be a mapping with type, base, extensions")
    block = cast("dict[str, Any]", core)
    if "isa" in block:
        raise ValueError("core.isa: the key is called base")
    unknown = sorted(str(key) for key in block if key not in KEYS)
    if unknown:
        raise ValueError(f"core has unknown keys {unknown}; use {list(KEYS)}")
    missing = [key for key in KEYS if key not in block]
    if missing:
        raise ValueError(f"core.{missing[0]} is required")
    kind, base = block["type"], str(block["base"]).lower()
    if isinstance(kind, bool) or kind not in TYPES:
        raise ValueError(f"core.type must be 32 or 64, not {kind!r}")
    if base not in ("i", "e"):
        raise ValueError(f"core.base must be I or E, not {block['base']!r}")
    return kind, base, _extensions(block["extensions"], known)


def _extensions(raw: Any, known: dict[str, str]) -> list[str]:
    """Read the list of extensions of the block.

    Parameters
    ----------
    raw : Any
        The value of `core.extensions`.
    known : dict of {str: str}
        The extensions that may be listed, by lower-case name.

    Returns
    -------
    list of str
        The extensions, canonical, in the order written; `Zicsr` leaves
        when `Zicntr` or `Zihpm` is there.

    Raises
    ------
    ValueError
        If the value is not a list, or an extension is unknown or
        repeated.
    """
    if not isinstance(raw, list):
        raise ValueError("core.extensions must be a list (or [])")
    found: list[str] = []
    for item in cast("list[Any]", raw):
        name = known.get(str(item).lower())
        if name is None:
            raise ValueError(
                f"core.extensions: unknown extension {item!r}; "
                f"known: {', '.join(known.values())}"
            )
        if name in found:
            raise ValueError(f"core.extensions: {name} is listed twice")
        found.append(name)
    if any(name in found for name in IMPLYING_ZICSR):
        found = [name for name in found if name != "Zicsr"]
    return found


def _profile(
    kind: int, base: str, wanted: list[str], spec: profiles.Spec
) -> str:
    """Find the profile of the specification for a base and extensions.

    Parameters
    ----------
    kind : int
        32 or 64.
    base : str
        `i` or `e`.
    wanted : list of str
        The extensions the specification lists.
    spec : profiles.Spec
        The specification.

    Returns
    -------
    str
        The name of the profile.

    Raises
    ------
    ValueError
        If the specification has no such base or refuses the
        combination.
    """
    prefix = f"rv{kind}{base}"
    bases = [b.name for b in spec.bases]
    if prefix not in bases:
        what = f"base {base.upper()}" if kind == RV32 else f"type {kind}"
        raise ValueError(
            f"core: {what} needs a base {prefix} in the profile "
            f"specification (it has {', '.join(bases)})"
        )
    for found in profiles.expand(spec):
        if found.base == prefix and set(found.extensions) == set(wanted):
            return found.name
    raise ValueError(
        f"core: the specification refuses {prefix} with "
        f"{', '.join(wanted) or 'no extension'}"
    )


def _plain_name(kind: int, base: str, wanted: list[str], named: bool) -> str:
    """Name the profile of a platform that has no specification.

    Parameters
    ----------
    kind : int
        32 or 64.
    base : str
        `i` or `e`.
    wanted : list of str
        The extensions of the specification of the Core.
    named : bool
        False when `--profile` replaces the name, which is then only
        the base.

    Returns
    -------
    str
        The base, `m` when `M` is there and the other extensions in
        the order of the matrix of the Core.
    """
    head = f"rv{kind}{base}"
    if not named:
        return head
    head += "m" if "M" in wanted else ""
    order = (
        "Zicclsm",
        "Zicsr",
        "Zicntr",
        "Zihpm",
        "Zifencei",
        "Zimop",
        "Zicond",
        "Zmmul",
    )
    return "_".join([head, *(n.lower() for n in order if n in wanted)])


def infer(
    core: Any,
    spec_path: Path | None,
    *,
    check_profile: bool = True,
) -> tuple[str, list[str]]:
    """Infer the profile and the extras from a `core` block.

    Parameters
    ----------
    core : Any
        The `core` block.
    spec_path : Path or None
        The specification of the profiles; None when the platform has
        no `profiles`, and the name then follows the order of the matrix
        of the Core.
    check_profile : bool, optional
        False when `--profile` replaces the profile, so the extensions
        of the block need not form a profile of the specification.

    Returns
    -------
    tuple of (str, list of str)
        The name of the profile and the extras, in the order of
        `EXTRAS`.

    Raises
    ------
    ValueError
        If the block is not valid (see the module).
    """
    spec = None if spec_path is None else profiles.load_spec(spec_path)
    listed = tuple(e.name for e in spec.extensions) if spec else KNOWN
    known = _canonical(listed + KNOWN + EXTRAS)
    kind, base, found = _read(core, known)
    inside = {name.lower() for name in listed}
    wanted = [name for name in found if name.lower() in inside]
    extras = [
        name
        for name in EXTRAS + OPTIONAL
        if name in found and name not in wanted
    ]
    lost = [n for n in found if n not in wanted and n not in extras]
    if lost:
        raise ValueError(
            f"core.extensions: {lost[0]} is not in the specification "
            "of the profiles"
        )
    if spec is None:
        return _plain_name(kind, base, wanted, check_profile), extras
    if not check_profile:
        return f"rv{kind}{base}", extras
    return _profile(kind, base, wanted, spec), extras


def normalize(
    data: dict[str, Any], platform_file: Path, *, replaced: bool = False
) -> None:
    """Derive `profile` and `extras` from the `core` block.

    The rest of the Tools reads `profile` and `extras`, so a platform
    that has the block gets those two keys derived from it. A platform
    that still writes `profile` or `extras` is refused.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform as read, changed in place.
    platform_file : Path
        The platform YAML, which `profiles` is relative to.
    replaced : bool, optional
        True when `--profile` replaces the profile.

    Raises
    ------
    ValueError
        If the platform has `profile` or `extras`, or the block is not
        valid.
    """
    old = [key for key in ("profile", "extras") if key in data]
    if old:
        raise ValueError(
            f"{' and '.join(old)} no longer accepted: {_migration(data)}"
        )
    if "core" not in data:
        return
    ref = data.get("profiles")
    spec = None if ref is None else platform_file.parent / str(ref)
    data["profile"], data["extras"] = infer(
        data["core"], spec, check_profile=not replaced
    )
