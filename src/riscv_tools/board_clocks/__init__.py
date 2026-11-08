"""Plano de relógios de uma plataforma numa placa."""

from riscv_tools.board_clocks.core import (
    PLL_INSTANCE,
    ClockPlan,
    ClockRole,
    clock_plan,
)

__all__ = ["PLL_INSTANCE", "ClockPlan", "ClockRole", "clock_plan"]
