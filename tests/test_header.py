"""Tests for the rv32_test.h generated for the HTIF convention."""

import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.htif import generate_header, write_header

TOHOST = 0x0002FFF0


def test_addresses_follow_tohost() -> None:
    """The fromhost word sits 8 bytes above tohost."""
    text = generate_header(TOHOST)
    assert "RV32_TOHOST_ADDR   ((volatile unsigned int *)0x0002FFF0)" in text
    assert "RV32_FROMHOST_ADDR ((volatile unsigned int *)0x0002FFF8)" in text


def test_fail_encoding_and_model_macros() -> None:
    """A failure is (code << 1) | 1, with the ACT4 model macro names."""
    text = generate_header(0x43FFFFE8)
    assert "(code << 1) | 1" in text
    assert "#define RVMODEL_HALT_PASS" in text
    assert "#define RVMODEL_HALT_FAIL(code)" in text


def test_write_header(tmp_path: Path) -> None:
    """The file holds exactly the generated text."""
    out = tmp_path / "rv32_test.h"
    write_header(TOHOST, out)
    assert out.read_text(encoding="utf-8") == generate_header(TOHOST)


@pytest.mark.skipif(
    shutil.which("gcc") is None, reason="needs a host C compiler"
)
def test_header_compiles(tmp_path: Path) -> None:
    """Every macro of the header compiles without a warning."""
    write_header(TOHOST, tmp_path / "rv32_test.h")
    src = tmp_path / "t.c"
    src.write_text(
        '#include "rv32_test.h"\n'
        "void a(void) { RV32_PASS(); }\n"
        "void b(void) { RV32_FAIL(); }\n"
        "void c(void) { RV32_FAIL(7); }\n"
        "void d(int x) { RV32_FAIL(x + 2); }\n"
        "void e(void) { RVMODEL_HALT_PASS; }\n"
        "void f(void) { RVMODEL_HALT_FAIL(3); }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "gcc",
            "-fsyntax-only",
            "-Wall",
            "-Werror",
            "-I",
            str(tmp_path),
            str(src),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
