"""Fixtures shared by the whole test suite."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

GCC = "riscv32-unknown-elf-gcc"


@pytest.fixture
def build_bare_elf(
    tmp_path: Path,
) -> Callable[[str, str], Path]:
    """Return a function that links assembly and a script to an ELF."""

    def build(asm: str, script: str) -> Path:
        """Write asm and script to tmp_path, then link them."""
        src = tmp_path / "bare.S"
        src.write_text(asm)
        ld = tmp_path / "bare.ld"
        ld.write_text(script)
        elf = tmp_path / "bare.elf"
        subprocess.run(
            [
                GCC,
                "-march=rv32im",
                "-mabi=ilp32",
                "-nostdlib",
                "-nostartfiles",
                "-T",
                str(ld),
                str(src),
                "-o",
                str(elf),
            ],
            check=True,
        )
        return elf

    return build
