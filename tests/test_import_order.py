"""Nenhum módulo do pacote depende de outro ter sido importado antes."""

import subprocess
import sys

import pytest
from support import check_equal

MODULES = [
    "riscv_tools.settings",
    "riscv_tools.config_files",
    "riscv_tools.board_generate",
    "riscv_tools.cli",
    "riscv_tools.board_schema",
    "riscv_tools.board_schema.pins",
    "riscv_tools.board_check",
    "riscv_tools.board",
    "riscv_tools.orchestrator",
]


@pytest.mark.parametrize("module", MODULES)
def test_a_module_imports_first_in_a_fresh_interpreter(module: str) -> None:
    """Importa o módulo sozinho num interpretador novo."""
    done = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        check=False,
    )
    check_equal(done.returncode, 0, done.stderr)
