"""Gera o `.qpf` e o `.qsf` (sem os pinos) de um projeto do Quartus."""

from riscv_tools.quartus_project.core import (
    ProjectSpec,
    render_qpf,
    render_qsf,
)

__all__ = ["ProjectSpec", "render_qpf", "render_qsf"]
