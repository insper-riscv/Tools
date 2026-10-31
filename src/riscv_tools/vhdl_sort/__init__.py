"""Sort VHDL sources into GHDL-analyzable dependency order."""

from riscv_tools.vhdl_sort.core import topo_sort

__all__ = ["topo_sort"]
