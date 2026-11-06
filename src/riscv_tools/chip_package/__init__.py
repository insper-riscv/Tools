"""Gera o pacote VHDL com os tempos de um chip do catálogo."""

from riscv_tools.chip_package.core import (
    IoDelays,
    chip_io_delays,
    package_name,
    render_chip_package,
)

__all__ = [
    "IoDelays",
    "chip_io_delays",
    "package_name",
    "render_chip_package",
]
