"""Check that every hand-written copy of a platform's memory map agrees."""

from .core import (
    Mismatch,
    check_memory_map,
    evaluate,
    load_platform,
    symbols,
    validate_platform,
)

__all__ = [
    "Mismatch",
    "check_memory_map",
    "evaluate",
    "load_platform",
    "symbols",
    "validate_platform",
]
