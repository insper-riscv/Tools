"""Gera o projeto Quartus de uma plataforma numa placa."""

from riscv_tools.board_generate.core import (
    Generated,
    GenerateRequest,
    check_project,
    generate,
    write_project,
)

__all__ = [
    "GenerateRequest",
    "Generated",
    "check_project",
    "generate",
    "write_project",
]
