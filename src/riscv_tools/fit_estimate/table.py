"""The calibration table of a family: a datum, replaceable by a file.

``boards/calibration/<family>.yaml`` holds the unit, the coefficients
and the expected error of one family (section 7.2 of the plan). A
coefficient ``null`` is a measurement not yet made. The vocabulary of
extensions, extras and peripherals is the one of the catalogs of the
repository, passed by the caller: a key outside it is refused, so the
vocabulary lives in one place.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.fit_estimate.policy import MAX_LOGIC_ERROR_PCT

GROUPS = (
    "core",
    "extensions",
    "extras",
    "zihpm",
    "cache",
    "peripherals",
    "backends",
)
ZIHPM_KEYS = ("a0", "a1", "a2")
CACHE_KEYS = ("icache", "dcache")
CACHE_TERMS = ("c0", "c1")
CORE_KEYS = ("rv32i", "rv32e")
SCALARS = ("per_block_glue",)
UNITS = ("alm", "le")


@dataclass(frozen=True)
class Vocabulary:
    """The names a table may use, from the catalogs of the repository.

    Parameters
    ----------
    extensions : frozenset of str
        ``extensions`` of the ``matrix.yaml`` of the Core.
    extras : frozenset of str
        ``extras`` of the ``platform.yaml``.
    peripherals : frozenset of str
        ``peripherals`` of the ``platform.yaml``.
    backends : frozenset of str
        Controllers of device (``sdram_16``, ``nor``, ...).
    """

    extensions: frozenset[str]
    extras: frozenset[str]
    peripherals: frozenset[str]
    backends: frozenset[str]


DEFAULT_VOCABULARY = Vocabulary(
    extensions=frozenset(
        {
            "Zicclsm",
            "Zicsr",
            "Zicntr",
            "Zifencei",
            "Zimop",
            "Zicond",
            "Zmmul",
            "M",
        }
    ),
    extras=frozenset({"Zihintntl", "Zihintpause", "Interrupts", "Sscofpmf"}),
    peripherals=frozenset(
        {
            "CLINT",
            "PLIC_base",
            "PLIC_per_source",
            "UART",
            "DISPLAY",
            "FLASH_CTRL",
        }
    ),
    backends=frozenset({"sdram_16", "sdram_32", "nor", "sram"}),
)


@dataclass(frozen=True)
class CalibrationTable:
    """The calibration of one family.

    Parameters
    ----------
    family : str
        Identifier of the family.
    unit : str
        ``"alm"`` or ``"le"``.
    coefficients : dict of {str: float or None}
        Flat map from a path (``core.rv32i``, ``zihpm.a1``,
        ``cache.icache.c1``, ``per_block_glue``) to the coefficient.
    error : dict of {str: Any}
        ``rms_pct``, ``max_pct``, ``holdout`` and ``map_to_fit_ratio``.
    fmax : dict of {str: Any}
        Frequency measured by grade.
    meta : dict of {str: Any}
        Tool, profiles of the fit and notes, kept as they are.
    """

    family: str
    unit: str
    coefficients: dict[str, float | None]
    error: dict[str, Any] = field(default_factory=dict[str, Any])
    fmax: dict[str, Any] = field(default_factory=dict[str, Any])
    meta: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def logic_error_enabled(self) -> bool:
        """Tell whether the family may fail on estimated logic (V12)."""
        worst = self.error.get("max_pct")
        return worst is not None and float(worst) <= MAX_LOGIC_ERROR_PCT

    @property
    def map_to_fit_ratio(self) -> float | None:
        """Ratio fit / synthesis estimate, None when not measured."""
        ratio = self.error.get("map_to_fit_ratio")
        return None if ratio is None else float(ratio)


def flatten(coefficients: Mapping[str, Any]) -> dict[str, float | None]:
    """Turn the nested ``coefficients`` section into path keys.

    Parameters
    ----------
    coefficients : mapping
        The ``coefficients`` section of the file.

    Returns
    -------
    dict of {str: float or None}
        One entry per leaf.
    """
    flat: dict[str, float | None] = {}
    _walk("", coefficients, flat)
    return flat


def _walk(prefix: str, node: Any, flat: dict[str, float | None]) -> None:
    """Add to ``flat`` the leaves under ``node``, by path."""
    if not isinstance(node, Mapping):
        flat[prefix] = None if node is None else float(node)
        return
    for key, value in cast("Mapping[str, Any]", node).items():
        _walk(f"{prefix}.{key}" if prefix else str(key), value, flat)


def nest(flat: Mapping[str, float | None]) -> dict[str, Any]:
    """Rebuild the nested section from path keys (inverse of flatten).

    Parameters
    ----------
    flat : mapping
        Path keys with their coefficients.

    Returns
    -------
    dict of {str: Any}
        The nested ``coefficients`` section.
    """
    nested: dict[str, Any] = {}
    for path, value in flat.items():
        node = nested
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return nested


def allowed_paths(vocabulary: Vocabulary | None) -> set[str] | None:
    """Return every legal coefficient path.

    Parameters
    ----------
    vocabulary : Vocabulary or None
        Catalog names, None when they are unknown.

    Returns
    -------
    set of str or None
        The paths of the schema, None without a vocabulary.
    """
    if vocabulary is None:
        return None
    paths = {f"core.{key}" for key in CORE_KEYS}
    paths |= {f"extensions.{key}" for key in vocabulary.extensions}
    paths |= {f"extras.{key}" for key in vocabulary.extras}
    paths |= {f"zihpm.{key}" for key in ZIHPM_KEYS}
    paths |= {
        f"cache.{cache}.{term}" for cache in CACHE_KEYS for term in CACHE_TERMS
    }
    paths |= {f"peripherals.{key}" for key in vocabulary.peripherals}
    paths |= {f"backends.{key}" for key in vocabulary.backends}
    paths |= set(SCALARS)
    return paths


def _checked_coefficients(
    data: Mapping[str, Any], vocabulary: Vocabulary | None
) -> dict[str, float | None]:
    """Flatten the coefficients of a table and refuse the illegal."""
    raw = cast("Mapping[str, Any]", data.get("coefficients") or {})
    for group in raw:
        if group not in (*GROUPS, *SCALARS):
            msg = f"unknown coefficient group '{group}'"
            raise ValueError(msg)
    try:
        flat = flatten(raw)
    except (TypeError, ValueError) as error:
        msg = f"coefficient is not a number: {error}"
        raise ValueError(msg) from error
    allowed = allowed_paths(vocabulary)
    for path in flat:
        if allowed is not None and path not in allowed:
            msg = f"coefficient '{path}' is not in the catalogs"
            raise ValueError(msg)
    return flat


def table_from_mapping(
    data: Mapping[str, Any], vocabulary: Vocabulary | None = None
) -> CalibrationTable:
    """Validate a table already read from YAML.

    Parameters
    ----------
    data : mapping
        Contents of ``boards/calibration/<family>.yaml``.
    vocabulary : Vocabulary, optional
        Catalog names; with it a key outside the catalogs is refused.

    Returns
    -------
    CalibrationTable
        The table.

    Raises
    ------
    ValueError
        On a missing field, a unit that is not ``alm`` or ``le``, a
        group outside the schema, a key outside the vocabulary or a
        coefficient that is not a number.
    """
    family = data.get("family")
    unit = data.get("unit")
    if not isinstance(family, str) or unit not in UNITS:
        msg = "table needs 'family' and a 'unit' of alm or le"
        raise ValueError(msg)
    flat = _checked_coefficients(data, vocabulary)
    known = {
        key: value
        for key, value in data.items()
        if key not in ("family", "unit", "coefficients", "error", "fmax")
    }
    return CalibrationTable(
        family=family,
        unit=str(unit),
        coefficients=flat,
        error=dict(cast("Mapping[str, Any]", data.get("error") or {})),
        fmax=dict(cast("Mapping[str, Any]", data.get("fmax") or {})),
        meta=known,
    )


def load_table(
    path: Path, vocabulary: Vocabulary | None = None
) -> CalibrationTable:
    """Read a calibration table from a file.

    Parameters
    ----------
    path : Path
        ``boards/calibration/<family>.yaml``.
    vocabulary : Vocabulary, optional
        Catalog names, see table_from_mapping.

    Returns
    -------
    CalibrationTable
        The table.

    Raises
    ------
    ValueError
        As table_from_mapping, or when the file is not a mapping.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        msg = f"{path}: not a mapping"
        raise ValueError(msg)
    return table_from_mapping(cast("Mapping[str, Any]", data), vocabulary)


def empty_table(
    family: str, unit: str, paths: Iterable[str] = ()
) -> CalibrationTable:
    """Make a table with no measurement (every coefficient null).

    Parameters
    ----------
    family : str
        Identifier of the family.
    unit : str
        ``"alm"`` or ``"le"``.
    paths : iterable of str, optional
        Coefficient paths to list as null.

    Returns
    -------
    CalibrationTable
        A table for which the estimator only emits V18.
    """
    return CalibrationTable(
        family=family,
        unit=unit,
        coefficients=dict.fromkeys(paths),
    )
