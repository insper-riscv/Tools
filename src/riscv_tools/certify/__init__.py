"""Build and run the ACT4 certification suite under cocotb/GHDL."""

from riscv_tools.certify.board import run_suite_on_board
from riscv_tools.certify.core import build_elfs, discover_elfs, run_suite

__all__ = ["build_elfs", "discover_elfs", "run_suite", "run_suite_on_board"]
