"""Edit a project's PLL source to reprogram its output clock frequency."""

from .core import get_pll_freq, set_pll_freq

__all__ = ["get_pll_freq", "set_pll_freq"]
