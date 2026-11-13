"""The list of profiles to measure, read from a data file.

``boards/calibration/profiles/<family>.yaml`` names the profiles of
section 7.6 of the plan: for each one, what to change in the
``platform.yaml`` of the project and which generics to pass to the
compile command. The profile name is the one of the Core's matrix
(``rv32im_zicntr_zifencei``), and the base and the extensions are read
from it.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.fit_estimate import ProfileSpec
from riscv_tools.memory_map.core_profile import NAME_ORDER

DEFAULT_HPM_COUNTERS = 29
DEFAULT_HPM_WIDTH = 64
KNOWN_EXTENSIONS = NAME_ORDER
BASES = ("rv32i", "rv32e")
GENERIC_HPM_COUNTERS = "HPM_COUNTERS"
GENERIC_HPM_WIDTH = "HPM_WIDTH"


@dataclass(frozen=True)
class ProfileDef:
    """One profile to measure.

    Parameters
    ----------
    id : str
        Name of the record (``p4_hpm_4x40``).
    group : int
        Row of the table of section 7.6 of the plan (1 to 9).
    profile : str
        Name of the profile of the Core's matrix.
    extras : tuple of str
        ``extras`` of the platform for this run.
    icache_kbit : int
        Instruction cache in kbit.
    dcache_kbit : int
        Data cache in kbit.
    generics : dict of {str: int}
        Generics of the top passed to the compile command.
    holdout : bool
        Left out of the fit, to validate it.
    outside : bool
        Measured but outside the linear domain of the model (for
        instance a cache the synthesis turns into registers): neither
        fitted nor counted in the errors.
    """

    id: str
    group: int
    profile: str
    extras: tuple[str, ...] = ()
    icache_kbit: int = 32
    dcache_kbit: int = 32
    generics: dict[str, int] = field(default_factory=dict[str, int])
    holdout: bool = False
    outside: bool = False


@dataclass(frozen=True)
class ProfileList:
    """The measurement plan of one family.

    Parameters
    ----------
    family : str
        Identifier of the family.
    unit : str
        ``"alm"`` or ``"le"``.
    platform : str
        Platform YAML of the project, relative to its root.
    synth : str
        Compile script of the project, relative to its root; empty when
        the project is written by ``board generate`` (``board`` is set).
    qsf : str
        Quartus settings file, relative to its root; empty with
        ``board``.
    seed : int
        Seed of the placement passed to the script.
    bits_per_block : int
        Bits of a block of RAM of the family.
    reference_kbit : int
        Cache size that the base term already contains.
    fixed : dict of {str: float}
        Terms held at a value (the ones the fixed top absorbs).
    known_fit : dict of {str: Any}
        ``profile`` and ``alms`` (a range) known after the fit.
    profiles : tuple of ProfileDef
        The profiles.
    board : str
        Board of ``boards/``; when set the harness writes the project
        with ``board generate`` and compiles it with the single compile
        script of ``program`` instead of the hand-written script.
    targets : tuple of str
        Components whose source closure ``board generate`` lists in the
        project (``--target``), plus the package of the memory map.
    """

    family: str
    unit: str
    platform: str
    synth: str
    qsf: str
    seed: int
    bits_per_block: int
    reference_kbit: int
    fixed: dict[str, float]
    known_fit: dict[str, Any]
    profiles: tuple[ProfileDef, ...]
    board: str = ""
    targets: tuple[str, ...] = ()


def parse_profile_name(name: str) -> tuple[str, frozenset[str]]:
    """Split a profile name into the base and the extensions.

    Parameters
    ----------
    name : str
        ``rv32i``, ``rv32im``, ``rv32im_zicntr_zifencei``, ...

    Returns
    -------
    tuple
        ``"rv32i"`` or ``"rv32e"``, and the set of extensions (``M`` and
        the names of the Z extensions).

    Raises
    ------
    ValueError
        On an unknown base or extension.
    """
    head, *rest = name.split("_")
    base = head[:5]
    if base not in BASES:
        msg = f"unknown base in profile '{name}'"
        raise ValueError(msg)
    letters = head[5:]
    if letters not in ("", "m"):
        msg = f"unknown letter '{letters}' in profile '{name}'"
        raise ValueError(msg)
    found = {"M"} if letters == "m" else set[str]()
    by_lower = {item.lower(): item for item in KNOWN_EXTENSIONS}
    for token in rest:
        if token not in by_lower:
            msg = f"unknown extension '{token}' in profile '{name}'"
            raise ValueError(msg)
        found.add(by_lower[token])
    return base, frozenset(found)


def spec_of(definition: ProfileDef) -> ProfileSpec:
    """Build the estimator's view of a profile.

    Parameters
    ----------
    definition : ProfileDef
        The profile.

    Returns
    -------
    ProfileSpec
        Base, extensions, extras, Zihpm size and caches. Peripherals,
        backends and memories stay empty: the fixed top of the project
        carries them in every measurement.
    """
    base, extensions = parse_profile_name(definition.profile)
    return ProfileSpec(
        base=base,
        extensions=extensions,
        extras=frozenset(definition.extras),
        hpm_counters=definition.generics.get(
            GENERIC_HPM_COUNTERS, DEFAULT_HPM_COUNTERS
        ),
        hpm_width=definition.generics.get(
            GENERIC_HPM_WIDTH, DEFAULT_HPM_WIDTH
        ),
        icache_kbit=float(definition.icache_kbit),
        dcache_kbit=float(definition.dcache_kbit),
    )


def _profile(entry: Mapping[str, Any]) -> ProfileDef:
    """Read one entry of the ``profiles`` list."""
    generics = cast("Mapping[str, int]", entry.get("generics") or {})
    return ProfileDef(
        id=str(entry["id"]),
        group=int(entry["group"]),
        profile=str(entry["profile"]),
        extras=tuple(str(item) for item in entry.get("extras") or ()),
        icache_kbit=int(entry.get("icache_kbit", 32)),
        dcache_kbit=int(entry.get("dcache_kbit", 32)),
        generics={str(k): int(v) for k, v in generics.items()},
        holdout=bool(entry.get("holdout", False)),
        outside=bool(entry.get("outside", False)),
    )


def _floats(node: Any) -> dict[str, float]:
    """Read a mapping of numbers, empty for a missing section."""
    items = cast("Mapping[str, Any]", node or {})
    return {str(key): float(value) for key, value in items.items()}


def load_profile_list(path: Path) -> ProfileList:
    """Read the measurement plan of a family.

    Parameters
    ----------
    path : Path
        ``boards/calibration/profiles/<family>.yaml``.

    Returns
    -------
    ProfileList
        The plan.

    Raises
    ------
    ValueError
        On a missing field, a repeated id or a profile name the matrix
        cannot make.
    """
    data = cast(
        "Mapping[str, Any]", yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    try:
        project = cast("Mapping[str, Any]", data["project"])
        profiles = tuple(_profile(entry) for entry in data["profiles"])
        plan = ProfileList(
            family=str(data["family"]),
            unit=str(data["unit"]),
            platform=str(project["platform"]),
            synth=str(project.get("synth", "")),
            qsf=str(project.get("qsf", "")),
            seed=int(project.get("seed", 5)),
            bits_per_block=int(data["bits_per_block"]),
            reference_kbit=int(data.get("reference_kbit", 0)),
            fixed=_floats(data.get("fixed")),
            known_fit=dict(
                cast("Mapping[str, Any]", data.get("known_fit") or {})
            ),
            profiles=profiles,
            board=str(project.get("board", "")),
            targets=tuple(str(item) for item in project.get("targets") or ()),
        )
        if not plan.board and not (plan.synth and plan.qsf):
            msg = "the project names neither a board nor synth and qsf"
            raise KeyError(msg)
    except (KeyError, TypeError) as error:
        msg = f"{path}: incomplete profile list ({error!r})"
        raise ValueError(msg) from error
    ids = [item.id for item in profiles]
    if len(set(ids)) != len(ids):
        msg = f"{path}: repeated profile id"
        raise ValueError(msg)
    for item in profiles:
        parse_profile_name(item.profile)
    return plan
