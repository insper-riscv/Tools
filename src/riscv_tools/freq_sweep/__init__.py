"""Edit a project's PLL source to reprogram its output clock."""

from riscv_tools.freq_sweep.core import PllParams, get_pll_freq, set_pll_freq

__all__ = ["PllParams", "get_pll_freq", "set_pll_freq"]
