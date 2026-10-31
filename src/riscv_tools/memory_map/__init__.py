"""Check that every copy of a platform's memory map agrees."""

from riscv_tools.memory_map.checks import check_memory_map
from riscv_tools.memory_map.core import Mismatch, load_platform, symbols
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.validation import validate_platform

__all__ = [
    "Mismatch",
    "check_memory_map",
    "evaluate",
    "load_platform",
    "symbols",
    "validate_platform",
]
