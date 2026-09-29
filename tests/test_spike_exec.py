import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.spike_exec import (
    prepared_elf,
    require_spike,
    spike_command,
    symbol_address,
)

GCC = "riscv32-unknown-elf-gcc"
NM = "riscv32-unknown-elf-nm"
OBJCOPY = "riscv32-unknown-elf-objcopy"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "htif_min"

needs_toolchain = pytest.mark.skipif(
    shutil.which(GCC) is None, reason=f"needs {GCC} on PATH"
)


def _fake_spike(tmp_path: Path, name: str, stderr: str) -> Path:
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\necho '{stderr}' >&2\nexit 255\n")
    script.chmod(0o755)
    return script


def test_require_spike_missing_binary_points_at_setup_doc() -> None:
    with pytest.raises(FileNotFoundError, match=r"SPIKE_SETUP\.md"):
        require_spike("spike-that-does-not-exist")


def test_require_spike_rejects_debug_module_at_address_zero(tmp_path: Path) -> None:
    fake = _fake_spike(
        tmp_path, "spike_unpatched", "devices at [0, 1000) and [0, 10000) overlap"
    )

    with pytest.raises(RuntimeError, match="debug module"):
        require_spike(str(fake))


def test_require_spike_accepts_a_binary_without_the_overlap(tmp_path: Path) -> None:
    fake = _fake_spike(tmp_path, "spike_patched", "some other error")

    assert require_spike(str(fake)) == str(fake)


def test_spike_command_lists_every_region_and_the_entry_point() -> None:
    cmd = spike_command(
        "spike",
        "rv32im",
        [(0, 0x8000), (0x8000, 0x1000)],
        0x40,
        Path("t.elf"),
        ("+signature=s.txt",),
    )

    assert cmd == [
        "spike",
        "--isa=rv32im",
        "-m0x0:0x8000,0x8000:0x1000",
        "--disable-dtb",
        "--pc=0x40",
        "+signature=s.txt",
        "t.elf",
    ]


@needs_toolchain
def test_prepared_elf_adds_fromhost_and_extra_symbols(tmp_path: Path) -> None:
    elf = tmp_path / "t.elf"
    subprocess.run(
        [
            GCC,
            "-march=rv32im",
            "-mabi=ilp32",
            "-nostdlib",
            "-nostartfiles",
            "-T",
            str(FIXTURES / "link.ld"),
            str(FIXTURES / "crt0.S"),
            str(FIXTURES / "pass_asm.S"),
            "-o",
            str(elf),
        ],
        check=True,
    )
    tohost = symbol_address(NM, elf, "tohost")

    with prepared_elf(
        OBJCOPY, NM, elf, "tohost", {"begin_signature": 0x80000100}
    ) as prepared:
        assert symbol_address(NM, prepared, "fromhost") == tohost + 8
        assert symbol_address(NM, prepared, "begin_signature") == 0x80000100

    assert not prepared.exists()
    with pytest.raises(RuntimeError, match="fromhost"):
        symbol_address(NM, elf, "fromhost")


@needs_toolchain
def test_prepared_elf_aliases_a_custom_tohost_symbol(tmp_path: Path) -> None:
    src = tmp_path / "a.S"
    src.write_text(
        ".globl _start\n_start: j _start\n"
        ".section .bss\n.balign 8\n.globl my_tohost\nmy_tohost: .space 8\n"
    )
    ld = tmp_path / "a.ld"
    ld.write_text(
        "ENTRY(_start)\n"
        "SECTIONS { . = 0x80000000; .text : { *(.text*) } .bss : { *(.bss*) } }\n"
    )
    elf = tmp_path / "a.elf"
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

    with prepared_elf(OBJCOPY, NM, elf, "my_tohost") as prepared:
        assert symbol_address(NM, prepared, "tohost") == symbol_address(
            NM, elf, "my_tohost"
        )
