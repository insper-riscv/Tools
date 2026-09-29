import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.compiler import elf_to_verilog_hex

GCC = "riscv32-unknown-elf-gcc"


@pytest.mark.skipif(shutil.which(GCC) is None, reason=f"needs {GCC} on PATH")
def test_elf_to_verilog_hex_keeps_the_real_word_address(tmp_path: Path) -> None:
    src = tmp_path / "f.S"
    src.write_text(
        ".section .text\n.globl _start\n_start:\n li t0, 1\n li t1, 2\n j _start\n"
        ".data\n.word 0xdeadbeef\n"
    )
    ld = tmp_path / "f.ld"
    ld.write_text(
        "ENTRY(_start)\n"
        "SECTIONS { . = 0x800; .text : { *(.text*) } .data : { *(.data*) } }\n"
    )
    elf = tmp_path / "f.elf"
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
    hex_path = tmp_path / "f.hex"

    elf_to_verilog_hex({"objcopy": "riscv32-unknown-elf-objcopy"}, elf, hex_path)

    assert hex_path.read_text().split("\n") == [
        "@00000200",
        "00100293 00200313 FF9FF06F",
        "@00000203",
        "DEADBEEF",
        "",
    ]
