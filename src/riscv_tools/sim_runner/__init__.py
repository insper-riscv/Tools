"""Drives cocotb/GHDL simulation — the sim-side counterpart to `orchestrator`."""

from .core import run_suite, run_test

__all__ = ["run_suite", "run_test"]
