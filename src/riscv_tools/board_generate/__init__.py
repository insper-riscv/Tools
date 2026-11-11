"""Gera o projeto Quartus de uma plataforma numa placa."""

from riscv_tools.board_generate.core import (
    Generated,
    GenerateRequest,
    check_project,
    generate,
    write_project,
)
from riscv_tools.board_generate.project import (
    ProjectRequest,
    ProjectResult,
    build,
    repository_root,
    request_from_config,
    sources_of,
    targets_of,
)

__all__ = [
    "GenerateRequest",
    "Generated",
    "ProjectRequest",
    "ProjectResult",
    "build",
    "check_project",
    "generate",
    "repository_root",
    "request_from_config",
    "sources_of",
    "targets_of",
    "write_project",
]
