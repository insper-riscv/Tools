"""Full recompile + quartus_pgm — the slow "base" bitstream path."""

from .core import full_reconfigure, program_only

__all__ = ["full_reconfigure", "program_only"]
