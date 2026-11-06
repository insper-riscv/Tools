"""Gera o projeto Quartus de uma plataforma numa placa."""

from riscv_tools.board_generate.core import (
    Generated,
    GenerateRequest,
    generate,
    write_project,
)

__all__ = ["GenerateRequest", "Generated", "generate", "write_project"]
