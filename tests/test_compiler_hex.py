"""Tests for compiler_hex."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from riscv_tools.compiler import elf_to_verilog_hex

GCC = "riscv32-unknown-elf-gcc"


@pytest.mark.skipif(shutil.which(GCC) is None, reason=f"needs {GCC} on PATH")
def test_elf_to_verilog_hex_keeps_the_real_word_address(
    tmp_path: Path,
    build_bare_elf: Callable[[str, str], Path],
) -> None:
    """Elf to verilog hex keeps the real word address."""
    elf = build_bare_elf(
        ".section .text\n.globl _start\n_start:\n"
        " li t0, 1\n li t1, 2\n j _start\n"
        ".data\n.word 0xdeadbeef\n",
        "ENTRY(_start)\n"
        "SECTIONS { . = 0x800; .text : { *(.text*) } "
        ".data : { *(.data*) } }\n",
    )
    hex_path = tmp_path / "f.hex"

    elf_to_verilog_hex(
        {"objcopy": "riscv32-unknown-elf-objcopy"}, elf, hex_path
    )

    assert hex_path.read_text().split("\n") == [
        "@00000200",
        "00100293 00200313 FF9FF06F",
        "@00000203",
        "DEADBEEF",
        "",
    ]
