"""Sort VHDL sources into GHDL-analyzable dependency order."""

from .core import topo_sort

__all__ = ["topo_sort"]
