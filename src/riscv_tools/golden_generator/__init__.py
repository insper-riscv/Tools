"""Generates a golden RAM reference by running a compiled test under Spike."""

from .core import generate_golden, symbol_range, write_golden_json

__all__ = ["generate_golden", "symbol_range", "write_golden_json"]
