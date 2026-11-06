"""The profile of a platform: its base ISA and the generics it turns on.

The platform picks its profile in `profile:` (`rv32im`,
`rv32em_zicsr`, ...) and says where the specification of the profiles is
in `profiles:`, a path relative to the platform file (the
`profiles/matrix.yaml` of the Core). `--profile NAME` of the command
line replaces the `profile:` of the platform, so a matrix of tests can
run the same platform over many profiles without editing it.

Zihintntl, Zihintpause and Interrupts (the machine interrupts, which
the core enables with Zicsr) are not in the specification of the Core
(Zimop and Zicond are), so the platform turns them on with `extras:
[Zihintntl, Zihintpause, Interrupts]`, which also survives
`--profile`. `extras` still accepts Zimop and Zicond. Every switch the profile and the extras do not turn on
comes out false.
"""

from pathlib import Path
from typing import Any, cast

from riscv_tools import profiles

NUM_REGS = {"i": 32, "e": 16}
SWITCHES = (
    "has_m",
    "has_zmmul",
    "has_zicsr",
    "has_zicntr",
    "has_zihpm",
    "has_zimop",
    "has_zicond",
    "has_zihintntl",
    "has_zihintpause",
    "has_zifencei",
    "has_zicclsm",
    "has_interrupts",
)

_override: list[str | None] = [None]


def set_override(name: str | None) -> None:
    """Replace the profile of every platform read from now on.

    Parameters
    ----------
    name : str or None
        The profile of `--profile`, or None to follow each platform.
    """
    _override[0] = name


def _base_of(name: str) -> str:
    """Read the base letter off the name of a profile.

    Parameters
    ----------
    name : str
        The profile name.

    Returns
    -------
    str
        `i` or `e`.

    Raises
    ------
    ValueError
        If the name does not start with `rv32i` or `rv32e`.
    """
    if name[:5] not in ("rv32i", "rv32e"):
        raise ValueError(f"profile {name!r} must start with rv32i or rv32e")
    return name[4]


def resolve(
    platform: dict[str, Any], platform_file: Path
) -> tuple[str, dict[str, bool | int]]:
    """Find the base ISA and the generics of the platform's profile.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `profile`, and `profiles` when the generics
        of the extensions are wanted.
    platform_file : Path
        The platform YAML, which `profiles` is relative to.

    Returns
    -------
    tuple of (str, dict)
        The base letter (`i` or `e`) and the generics of the profile:
        `num_regs` and the `has_*` switches. Without `profiles` only
        `num_regs` comes back.

    Raises
    ------
    ValueError
        If the name is not a profile of the specification, or the
        override has no specification to be found in.
    """
    name = str(_override[0] or platform.get("profile", "rv32i")).lower()
    spec_ref = platform.get("profiles")
    if spec_ref is None:
        if _override[0]:
            raise ValueError("--profile needs `profiles:` in the platform")
        base = _base_of(name)
        return base, {"num_regs": NUM_REGS[base]}
    found = {
        p.name: p
        for p in profiles.expand(
            profiles.load_spec(platform_file.parent / str(spec_ref))
        )
    }
    if name not in found:
        raise ValueError(f"{name!r} is not a profile of {spec_ref}")
    chosen = found[name]
    generics = dict.fromkeys(SWITCHES, False) | dict(chosen.generics)
    extras = cast("list[Any]", platform.get("extras") or [])
    for extra in extras:
        key = f"has_{str(extra).lower()}"
        if key not in SWITCHES:
            raise ValueError(f"extra {extra!r} is not one of {SWITCHES}")
        generics[key] = True
    return _base_of(name), generics
