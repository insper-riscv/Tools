"""Fit the coefficients of a family from the raw measurements.

The model is linear in the coefficients (section 7.2 of the plan), so
the fit is an ordinary least squares over the profiles that are not left
out. The terms of each profile come from ``fit_estimate.terms``, the
same function the estimator uses, and the error is measured by the
estimator's own sum, so the table and the estimator cannot disagree.
"""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.calibration.profiles import (
    ProfileDef,
    ProfileList,
    spec_of,
)
from riscv_tools.fit_estimate import (
    DEFAULT_VOCABULARY,
    CalibrationTable,
    allowed_paths,
    estimate_logic,
    nest,
    terms,
)

CACHES = ("icache", "dcache")
EPSILON = 1e-9
PERCENT = 100.0


def load_records(directory: Path) -> dict[str, dict[str, Any]]:
    """Read the raw records of a directory.

    Parameters
    ----------
    directory : Path
        ``boards/calibration/raw/<family>/``.

    Returns
    -------
    dict of {str: dict}
        Record by profile id.
    """
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        data = cast(
            "dict[str, Any]",
            yaml.safe_load(path.read_text(encoding="utf-8")),
        )
        records[str(data["id"])] = data
    return records


def _effective(
    values: Mapping[str, float], plan: ProfileList
) -> tuple[dict[str, float], float]:
    """Apply the fixed terms and the cache tie to a row of terms.

    The reference size of a cache is already in the base term, so the
    tie ``c0 = -reference * c1`` folds the column of ``c0`` into the one
    of ``c1``.

    Returns the free columns and the part of the value the fixed terms
    explain.
    """
    free = dict(values)
    fixed_part = 0.0
    for path, coefficient in plan.fixed.items():
        fixed_part += coefficient * free.pop(path, 0.0)
    for cache in CACHES:
        c0 = free.pop(f"cache.{cache}.c0", 0.0)
        if f"cache.{cache}.c1" in free:
            free[f"cache.{cache}.c1"] -= plan.reference_kbit * c0
    return free, fixed_part


def _least_squares(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, float]],
    y: Sequence[float],
) -> tuple[dict[str, float], list[str]]:
    """Solve by modified Gram-Schmidt, dropping dependent columns.

    Returns the coefficients and the columns that no combination of the
    earlier ones separates.
    """
    basis: list[tuple[str, list[float], list[float]]] = []
    dependent: list[str] = []
    for name in columns:
        vector = [row.get(name, 0.0) for row in rows]
        scale = math.sqrt(sum(v * v for v in vector))
        coeffs = [0.0] * len(basis)
        for index, (_, unit, _) in enumerate(basis):
            coeffs[index] = sum(
                a * b for a, b in zip(unit, vector, strict=True)
            )
            vector = [
                v - coeffs[index] * u
                for v, u in zip(vector, unit, strict=True)
            ]
        norm = math.sqrt(sum(v * v for v in vector))
        if norm <= EPSILON * max(scale, 1.0):
            dependent.append(name)
            continue
        basis.append((name, [v / norm for v in vector], [*coeffs, norm]))
    projections = [
        sum(a * b for a, b in zip(unit, y, strict=True))
        for _, unit, _ in basis
    ]
    solution = [0.0] * len(basis)
    for i in reversed(range(len(basis))):
        upper = sum(
            basis[j][2][i] * solution[j] for j in range(i + 1, len(basis))
        )
        solution[i] = (projections[i] - upper) / basis[i][2][i]
    return {b[0]: solution[i] for i, b in enumerate(basis)}, dependent


def _rows(
    plan: ProfileList, records: Mapping[str, Mapping[str, Any]]
) -> list[tuple[ProfileDef, dict[str, float], float]]:
    """Pair each measured profile with its terms and its logic."""
    out: list[tuple[ProfileDef, dict[str, float], float]] = []
    for definition in plan.profiles:
        record = records.get(definition.id)
        if record is None:
            continue
        logic = record["result"]["logic"]
        values = terms(spec_of(definition), plan.bits_per_block)
        out.append((definition, values, float(logic)))
    return out


def _coefficients(
    plan: ProfileList,
    fit_rows: Sequence[tuple[ProfileDef, dict[str, float], float]],
) -> tuple[dict[str, float | None], list[str]]:
    """Fit the free terms and lay out the whole schema."""
    free_rows: list[dict[str, float]] = []
    targets: list[float] = []
    for _, values, logic in fit_rows:
        free, fixed_part = _effective(values, plan)
        free_rows.append(free)
        targets.append(logic - fixed_part)
    columns: list[str] = []
    for free in free_rows:
        columns.extend(k for k, v in free.items() if v and k not in columns)
    solved, dependent = _least_squares(columns, free_rows, targets)
    paths = allowed_paths(DEFAULT_VOCABULARY) or set()
    coefficients: dict[str, float | None] = dict.fromkeys(sorted(paths))
    coefficients.update({k: round(v, 3) for k, v in solved.items()})
    coefficients.update(plan.fixed)
    for cache in CACHES:
        c1 = coefficients.get(f"cache.{cache}.c1")
        if c1 is not None:
            coefficients[f"cache.{cache}.c0"] = round(
                -plan.reference_kbit * c1, 3
            )
    return coefficients, dependent


def _errors(
    plan: ProfileList,
    table: CalibrationTable,
    rows: Sequence[tuple[ProfileDef, dict[str, float], float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Measure the residual of each profile with the estimator's sum."""
    residuals: list[dict[str, Any]] = []
    for definition, _, logic in rows:
        predicted, missing = estimate_logic(
            spec_of(definition), table, plan.bits_per_block
        )
        residuals.append(
            {
                "id": definition.id,
                "holdout": definition.holdout,
                "measured": logic,
                "predicted": round(predicted, 1),
                "error_pct": round(100 * (predicted - logic) / logic, 3),
                "missing": list(missing),
            }
        )
    fit = [r["error_pct"] for r in residuals if not r["holdout"]]
    held = [abs(r["error_pct"]) for r in residuals if r["holdout"]]
    error = {
        "rms_pct": round(math.sqrt(sum(e * e for e in fit) / len(fit)), 3),
        "max_fit_pct": round(max(abs(e) for e in fit), 3),
        "max_pct": round(max(held), 3) if held else None,
        "holdout": [r["id"] for r in residuals if r["holdout"]],
    }
    return residuals, error


def known_fit_check(
    plan: ProfileList,
    rows: Sequence[tuple[ProfileDef, dict[str, float], float]],
) -> dict[str, Any] | None:
    """Compare the synthesis estimate with the fit known for a profile.

    Returns
    -------
    dict or None
        The synthesis estimate, the known fit range and the ratio
        fit / synthesis at both ends; None without a measured profile.
    """
    known = plan.known_fit
    for definition, _, logic in rows:
        if definition.id == known.get("profile"):
            low, high = (float(x) for x in known["alms"])
            return {
                "profile": definition.id,
                "map_estimate": logic,
                "known_fit_range": [low, high],
                "ratio_low": round(low / logic, 4),
                "ratio_high": round(high / logic, 4),
                "ratio_mid": round((low + high) / 2 / logic, 4),
            }
    return None


def fit_table(
    plan: ProfileList, records: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Fit a family and build the content of its calibration file.

    Parameters
    ----------
    plan : ProfileList
        The family's plan.
    records : mapping
        Raw records by profile id (see load_records).

    Returns
    -------
    dict of {str: Any}
        The calibration table in the schema of section 7.2 of the plan,
        with the residuals of every profile.

    Raises
    ------
    ValueError
        When no profile of the plan has a record.
    """
    rows = _rows(plan, records)
    fit_rows = [row for row in rows if not row[0].holdout]
    if not fit_rows:
        msg = "no measured profile to fit"
        raise ValueError(msg)
    coefficients, dependent = _coefficients(plan, fit_rows)
    check = known_fit_check(plan, rows)
    table = CalibrationTable(plan.family, plan.unit, coefficients)
    residuals, error = _errors(plan, table, rows)
    error["map_to_fit_ratio"] = check["ratio_mid"] if check else None
    result = _description(plan, records, fit_rows)
    result.update(
        {
            "unseparated": dependent,
            "coefficients": nest(coefficients),
            "error": error,
            "known_fit_check": check,
            "fmax": {"core_mhz_by_grade": {"C7": None}},
            "residuals": residuals,
        }
    )
    return result


def _description(
    plan: ProfileList,
    records: Mapping[str, Mapping[str, Any]],
    fit_rows: Sequence[tuple[ProfileDef, dict[str, float], float]],
) -> dict[str, Any]:
    """Describe what the fit was made from (tool, hashes, revisions)."""
    revs = {
        str(r.get("revisions", {}).get("Core"))
        for r in records.values()
        if r.get("revisions")
    }
    return {
        "family": plan.family,
        "unit": plan.unit,
        "tool": next(iter(records.values()))["tool"],
        "unit_basis": "quartus_map estimate",
        "fitted_on": [
            {
                "profile": d.id,
                "seed": plan.seed,
                "sources_hash": records[d.id]["sources_hash"],
            }
            for d, _, _ in fit_rows
        ],
        "core_revisions": sorted(revs),
        "reference_kbit": plan.reference_kbit,
        "absorbed": sorted(plan.fixed),
    }


def write_table(content: Mapping[str, Any], path: Path) -> None:
    """Write the calibration file.

    Parameters
    ----------
    content : mapping
        What fit_table returned.
    path : Path
        ``boards/calibration/<family>.yaml``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(content), sort_keys=False), encoding="utf-8"
    )
