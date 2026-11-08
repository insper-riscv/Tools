"""Fixtures shared by the whole test suite."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from support import link_bare

from riscv_tools.memory_map import set_override


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


@pytest.fixture(autouse=True)
def reset_profile_override() -> Iterator[None]:
    """Run every test with the profile that its platform names."""
    set_override(None)
    yield
    set_override(None)
