"""Check that every copy of a platform's memory map agrees."""

from riscv_tools.memory_map.checks import check_memory_map
from riscv_tools.memory_map.config_view import config_from_platform
from riscv_tools.memory_map.core import Mismatch, load_platform, symbols
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.generate import check_all, render_all, write_all
from riscv_tools.memory_map.profile import resolve, set_override
from riscv_tools.memory_map.validation import validate_platform

__all__ = [
    "Mismatch",
    "check_all",
    "check_memory_map",
    "config_from_platform",
    "evaluate",
    "load_platform",
    "render_all",
    "resolve",
    "set_override",
    "symbols",
    "validate_platform",
    "write_all",
]
