"""Runs a compiled test's ELF under Spike and reports PASS/FAIL."""

from .core import SpikeRunResult, run_elf

__all__ = ["SpikeRunResult", "run_elf"]
