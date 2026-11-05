"""Check that VHDL files follow the style guide of the project."""

from riscv_tools.vhdl_style.core import (
    check_vhdl_style,
    is_generated_ip,
    rule_names,
)

__all__ = ["check_vhdl_style", "is_generated_ip", "rule_names"]
