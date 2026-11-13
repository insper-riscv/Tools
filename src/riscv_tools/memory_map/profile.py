"""The profile of a platform: its base ISA and the generics it turns on.

The platform picks its profile in `profile:` (`rv32im`,
`rv32em_zicsr`, ...) and says where the specification of the profiles is
in `profiles:`, a path relative to the platform file (the
`profiles/matrix.yaml` of the Core). `--profile NAME` of the command
line replaces the `profile:` of the platform, so a matrix of tests can
run the same platform over many profiles without editing it.

Zihintntl, Zihintpause, Interrupts (the machine interrupts, which
the core enables with Zicsr) and Sscofpmf (the counter-overflow
interrupt, which needs Zihpm and Interrupts) and AccessFaults (the
access-fault exceptions of the memory map) are not in the
specification of the Core (Zimop and Zicond are), so the platform turns
them on with `extras: [Zihintntl, Zihintpause, Interrupts, Sscofpmf]`,
which also survives `--profile`. `extras` still accepts Zimop and
Zicond. Every switch the profile and the extras do not turn on comes
out false.
"""

import re
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
    "has_sscofpmf",
    "has_access_faults",
)

RV32_XLEN = 32
RV64_XLEN = 64
_XLEN_OF_PREFIX = {"rv32": RV32_XLEN, "rv64": RV64_XLEN}

_override: list[str | None] = [None]


def set_override(name: str | None) -> None:
    """Replace the profile of every platform read from now on.

    Parameters
    ----------
    name : str or None
        The profile of `--profile`, or None to follow each platform.
    """
    _override[0] = name


def _base_of(name: str) -> tuple[str, int]:
    """Read the base letter and the register width off a profile name.

    Parameters
    ----------
    name : str
        The profile name.

    Returns
    -------
    tuple of (str, int)
        The base letter, `i` or `e`, and `xlen`, 32 for the `rv32`
        prefix and 64 for the `rv64` prefix.

    Raises
    ------
    ValueError
        If the name does not start with `rv32i`, `rv32e`, `rv64i` or
        `rv64e`.
    """
    xlen = _XLEN_OF_PREFIX.get(name[:4])
    if xlen is None or name[4:5] not in ("i", "e"):
        raise ValueError(
            f"profile {name!r} must start with rv32i, rv32e, rv64i or rv64e"
        )
    return name[4], xlen


def profile_name(platform: dict[str, Any]) -> str:
    """Name the profile of the platform, the override included.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        The `--profile` override when there is one, else the `profile`
        of the platform (`rv32i` when it names none), in lower case.
    """
    return str(_override[0] or platform.get("profile", "rv32i")).lower()


def xlen_of(platform: dict[str, Any]) -> int:
    """Read the register width of the platform's profile.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    int
        32 for an `rv32` profile and 64 for an `rv64` one.

    Raises
    ------
    ValueError
        If the profile name has no valid base prefix.
    """
    return _base_of(profile_name(platform))[1]


def _apply_extras(
    generics: dict[str, bool | int], platform: dict[str, Any]
) -> None:
    """Switch on the generics of the `extras` the platform lists.

    Raises
    ------
    ValueError
        If an extra is not a switch, or Sscofpmf lacks Zihpm or the
        interrupts.
    """
    extras = cast("list[Any]", platform.get("extras") or [])
    for extra in extras:
        key = "has_" + re.sub(r"(?<!^)(?=[A-Z])", "_", str(extra)).lower()
        if key not in SWITCHES:
            raise ValueError(f"extra {extra!r} is not one of {SWITCHES}")
        generics[key] = True
    if generics["has_sscofpmf"] and not (
        generics["has_zihpm"] and generics["has_interrupts"]
    ):
        raise ValueError(
            "extra 'Sscofpmf' needs Zihpm in the profile and the "
            "'Interrupts' extra"
        )


def resolve(
    platform: dict[str, Any], platform_file: Path
) -> tuple[str, dict[str, bool | int], int]:
    """Find the base ISA, the generics and the width of the profile.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `profile`, and `profiles` when the generics
        of the extensions are wanted.
    platform_file : Path
        The platform YAML, which `profiles` is relative to.

    Returns
    -------
    tuple of (str, dict, int)
        The base letter (`i` or `e`), the generics of the profile
        (`num_regs` and the `has_*` switches; without `profiles` only
        `num_regs`) and `xlen`, 32 for an `rv32` profile and 64 for an
        `rv64` one.

    Raises
    ------
    ValueError
        If the name is not a profile of the specification, has no valid
        base prefix, or the override has no specification to be found
        in.
    """
    name = profile_name(platform)
    spec_ref = platform.get("profiles")
    if spec_ref is None:
        if _override[0]:
            raise ValueError("--profile needs `profiles:` in the platform")
        base, xlen = _base_of(name)
        return base, {"num_regs": NUM_REGS[base]}, xlen
    found = {
        p.name: p
        for p in profiles.expand(
            profiles.load_spec(platform_file.parent / str(spec_ref))
        )
    }
    if name not in found:
        raise ValueError(f"{name!r} is not a profile of {spec_ref}")
    generics = dict.fromkeys(SWITCHES, False) | dict(found[name].generics)
    _apply_extras(generics, platform)
    base, xlen = _base_of(name)
    return base, generics, xlen


def profile_replaced() -> bool:
    """Say whether `--profile` replaces the profile of the platforms.

    Returns
    -------
    bool
        True when an override is set.
    """
    return bool(_override[0])
