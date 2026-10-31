"""Compose the other modules into a real-hardware test-suite run."""

from riscv_tools.orchestrator.failure import NeedsHumanInterventionError
from riscv_tools.orchestrator.jtag_run import (
    full_reconfigure_entry,
    run_test_via_jtag,
)
from riscv_tools.orchestrator.runner import run_one
from riscv_tools.orchestrator.suite import run_suite
from riscv_tools.orchestrator.sweep import (
    run_freq_sweep_at,
    run_freq_sweep_binary,
    run_freq_sweep_linear,
)

__all__ = [
    "NeedsHumanInterventionError",
    "full_reconfigure_entry",
    "run_freq_sweep_at",
    "run_freq_sweep_binary",
    "run_freq_sweep_linear",
    "run_one",
    "run_suite",
    "run_test_via_jtag",
]
