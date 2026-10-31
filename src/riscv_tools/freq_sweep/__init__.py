"""Edit a project's PLL source to reprogram its output clock."""

from riscv_tools.freq_sweep.core import PllParams, set_pll_freq

__all__ = ["PllParams", "set_pll_freq"]
