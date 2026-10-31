"""Fixtures shared by the whole test suite."""

from collections.abc import Callable
from pathlib import Path

import pytest
from support import link_bare


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
        link_bare([src], ld, elf)
        return elf

    return build
