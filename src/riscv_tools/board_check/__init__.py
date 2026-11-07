"""Check what a platform requires against what its boards provide."""

from riscv_tools.board_check.catalog_check import check_catalog
from riscv_tools.board_check.core import (
    check_platform,
    check_platform_file,
    fit_report,
)
from riscv_tools.board_check.findings import Finding
from riscv_tools.board_check.rules_board import check_chain

__all__ = [
    "Finding",
    "check_catalog",
    "check_chain",
    "check_platform",
    "check_platform_file",
    "fit_report",
]
