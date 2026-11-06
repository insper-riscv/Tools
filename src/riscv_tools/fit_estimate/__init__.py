"""Estimate whether a profile fits a board, and judge the result."""

from riscv_tools.fit_estimate.estimator import (
    Estimate,
    ProfileSpec,
    blocks_needed,
    estimate,
    estimate_logic,
    terms,
)
from riscv_tools.fit_estimate.policy import (
    Capacity,
    Finding,
    Level,
    capacity_from_resources,
    classify,
    load_capacity,
    report_findings,
)
from riscv_tools.fit_estimate.table import (
    DEFAULT_VOCABULARY,
    CalibrationTable,
    Vocabulary,
    allowed_paths,
    empty_table,
    flatten,
    load_table,
    nest,
    table_from_mapping,
)

__all__ = [
    "DEFAULT_VOCABULARY",
    "CalibrationTable",
    "Capacity",
    "Estimate",
    "Finding",
    "Level",
    "ProfileSpec",
    "Vocabulary",
    "allowed_paths",
    "blocks_needed",
    "capacity_from_resources",
    "classify",
    "empty_table",
    "estimate",
    "estimate_logic",
    "flatten",
    "load_capacity",
    "load_table",
    "nest",
    "report_findings",
    "table_from_mapping",
    "terms",
]
