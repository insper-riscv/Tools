"""Drives cocotb/GHDL simulation — the sim-side counterpart to `orchestrator`."""

from .core import build_libraries, expand_env, run_suite, run_test

__all__ = ["build_libraries", "expand_env", "run_suite", "run_test"]
