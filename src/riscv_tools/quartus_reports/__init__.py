"""Resources the Quartus reports after the synthesis and the fit."""

from riscv_tools.quartus_reports.core import (
    Entity,
    Quantity,
    ResourceUsage,
    parse_entities,
    parse_fit_report,
    parse_map_report,
    parse_quantity,
    parse_summary,
    succeeded,
)

__all__ = [
    "Entity",
    "Quantity",
    "ResourceUsage",
    "parse_entities",
    "parse_fit_report",
    "parse_map_report",
    "parse_quantity",
    "parse_summary",
    "succeeded",
]
