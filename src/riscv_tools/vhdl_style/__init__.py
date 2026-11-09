"""Check that VHDL files follow the style guide of the project."""

from riscv_tools.vhdl_style.core import check_vhdl_style
from riscv_tools.vhdl_style.files import is_generated_ip, vhdl_files
from riscv_tools.vhdl_style.runner import (
    BOARD_CONFIG,
    CONFIG,
    LOCAL_RULES,
    run_vsg,
)

__all__ = [
    "BOARD_CONFIG",
    "CONFIG",
    "LOCAL_RULES",
    "check_vhdl_style",
    "is_generated_ip",
    "run_vsg",
    "vhdl_files",
]
