"""Worst timing paths of a compiled Quartus project, grouped by register."""

from riscv_tools.timing_paths.core import (
    PathGroup,
    TimingPath,
    format_table,
    group_paths,
    parse_paths,
    register_of,
    run_timing_paths,
)

__all__ = [
    "PathGroup",
    "TimingPath",
    "format_table",
    "group_paths",
    "parse_paths",
    "register_of",
    "run_timing_paths",
]
