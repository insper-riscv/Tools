"""Build and run the ACT4 architectural certification suite under cocotb/GHDL."""

from .board import run_suite_on_board
from .core import build_elfs, discover_elfs, run_suite

__all__ = ["build_elfs", "discover_elfs", "run_suite", "run_suite_on_board"]
