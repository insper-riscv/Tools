"""End-to-end tests of the picolibc runtime, for a project with no crt0 or linker.

The project under test (see fixtures/platform_min/) describes its platform
in a GCC specs file (`toolchain.specs`), which selects the toolchain's own
crt0 and linker script and gives the memory map, and only supplies `_exit`,
the boot ROM and a Spike stand-in for the boot ROM's routine at the end of
a test. They prove: the tests compile and link with nothing but that file,
a program can return from main, Spike generates the goldens from the very
image the hardware loads, and the image starts where the boot ROM jumps.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from riscv_tools import run_log
from riscv_tools.cli import cmd_compile, cmd_spike_run
from riscv_tools.compiler import compile_test

GCC = "riscv32-unknown-elf-gcc"
NM = "riscv32-unknown-elf-nm"
SPIKE = "spike"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "platform_min"
ISA = {"base": "i", "default_ext": "", "canonical_order": "MAFDQLCBJTPVNH"}


def _has_picolibc() -> bool:
    if shutil.which(GCC) is None:
        return False
    probe = subprocess.run(
        [
            GCC,
            "--specs=picolibc.specs",
            "-E",
            "-x",
            "c",
            "/dev/null",
            "-o",
            "/dev/null",
        ],
        check=False,
        capture_output=True,
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _has_picolibc() or shutil.which(SPIKE) is None,
    reason=f"needs a {GCC} configured with picolibc, and {SPIKE}",
)


def _make_project(root: Path) -> None:
    shutil.copytree(FIXTURE, root / "platform")

    (root / "c" / "add").mkdir(parents=True)
    (root / "c" / "add" / "src.c").write_text(
        '#include "rv32_test.h"\n'
        "int main(void) {\n"
        "    if (6 * 7 == 42) { RV32_PASS(); }\n"
        "    RV32_FAIL();\n"
        "}\n"
    )

    (root / "c" / "mem").mkdir()
    (root / "c" / "mem" / "src.c").write_text(
        "// RV32_TEST_KIND: memory\n"
        '#include "rv32_test.h"\n'
        "volatile unsigned int results[1];\n"
        "int main(void) {\n"
        "    results[0] = 0x11111111u;\n"
        "    RV32_PASS();\n"
        "}\n"
    )

    # Declares `results` and never touches it: the linker must still keep
    # it, since the golden is read from it.
    (root / "c" / "declared").mkdir()
    (root / "c" / "declared" / "src.c").write_text(
        "// RV32_TEST_KIND: memory\n"
        '#include "rv32_test.h"\n'
        "volatile unsigned int results[1];\n"
        "int main(void) { RV32_PASS(); }\n"
    )

    # Returns from main, as any C program does: the crt0 calls exit().
    (root / "c" / "returns").mkdir()
    (root / "c" / "returns" / "src.c").write_text("int main(void) { return 0; }\n")

    # Initialized data, zero data and a constant: what the crt0 must copy,
    # clear and leave alone. A wrong value returns nonzero, which _exit
    # reports as FAIL.
    (root / "c" / "data").mkdir()
    (root / "c" / "data" / "src.c").write_text(
        'char text[7] = "abcdef";\n'
        "int word = 0x12345678;\n"
        "int zero;\n"
        "const int table[2] = {0x0BADF00D, 0x1234};\n"
        "volatile int selector = 1;\n"
        "int main(void) {\n"
        "    if (text[5] != 'f' || text[6] != 0) return 1;\n"
        "    if (word != 0x12345678) return 2;\n"
        "    if (zero != 0) return 3;\n"
        "    if (table[0] != 0x0BADF00D || table[selector] != 0x1234) return 4;\n"
        "    return 0;\n"
        "}\n"
    )

    (root / "asm" / "raw").mkdir(parents=True)
    (root / "asm" / "raw" / "src.S").write_text(
        ".section .text\n"
        ".globl main\n"
        "main:\n"
        "    lui  x15, 0x30\n"
        "    addi x14, x0, 1\n"
        "    sw   x14, -4(x15)\n"
        "    j    rv32_wait_restart\n"
    )

    include_dir = root / "include"
    include_dir.mkdir()
    (include_dir / "rv32_test.h").write_text(
        "#define RV32_MAILBOX_ADDR ((volatile unsigned int *)0x0002FFFC)\n"
        "extern void rv32_wait_restart(void) __attribute__((noreturn));\n"
        "static inline void RV32_PASS(void) { *RV32_MAILBOX_ADDR = 1; "
        "rv32_wait_restart(); }\n"
        "static inline void RV32_FAIL(void) { *RV32_MAILBOX_ADDR = 2; "
        "rv32_wait_restart(); }\n"
    )

    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "toolchain": {
                    "gcc": GCC,
                    "objcopy": "riscv32-unknown-elf-objcopy",
                    "specs": "platform/rv32im-fpga.specs",
                },
                "isa": ISA,
                "paths": {
                    "include_dir": "include",
                    "sources": ["platform/_exit.c"],
                    "boot_rom": "platform/boot_rom.S",
                    "boot_rom_linker_script": "platform/boot_rom.ld",
                    "build_dir": "build",
                    "c_dir": "c",
                    "asm_dir": "asm",
                },
                "emulator": {
                    "sources": ["platform/spike_exit.S"],
                    "gcc_flags": ["-DRV32_SPIKE"],
                },
                "quartus": {"default_timeout_s": 5},
                "memory": {
                    "rom_base": 0x800,
                    "rom_words": 7680,
                    "ram_base": 0x8000,
                    "ram_words": 40960,
                },
            }
        )
    )


def _args(root: Path, emit: str) -> Any:
    class _Args:
        config = str(root / "config.yaml")
        manifest = None
        manifest_per_test = None

    args = _Args()
    args.root = str(root)  # type: ignore[attr-defined]
    args.emit = emit  # type: ignore[attr-defined]
    return args


def _no_log(*_args: object, **_kwargs: object) -> None:
    return None


def _symbols(elf: Path) -> dict[str, int]:
    out = subprocess.run([NM, str(elf)], check=True, capture_output=True, text=True)
    return {
        line.split()[2]: int(line.split()[0], 16) for line in out.stdout.splitlines()
    }


def test_compile_needs_no_crt0_or_linker_script(tmp_path: Path) -> None:
    src = tmp_path / "src.c"
    src.write_text(
        '#include <string.h>\nint main(void) { return strlen("riscv") != 5; }\n'
    )

    bin_, _march, _kind, _timeout = compile_test(
        {
            "gcc": GCC,
            "objcopy": "riscv32-unknown-elf-objcopy",
            "specs": str(FIXTURE / "rv32im-fpga.specs"),
        },
        ISA,
        5.0,
        src,
        "strlen",
        tmp_path / "build",
        tmp_path,
        None,
        None,
        extra_sources=[FIXTURE / "_exit.c"],
    )

    syms = _symbols(tmp_path / "build" / "strlen.elf")
    assert bin_.is_file()
    # The toolchain's crt0 starts at the flash base the specs file gives.
    assert syms["_start"] == 0x800
    # The boot ROM's routine is at its fixed address, from the specs file.
    assert syms["rv32_wait_restart"] == 0x100


def test_cmd_compile_builds_every_kind_and_the_goldens(tmp_path: Path) -> None:
    _make_project(tmp_path)

    cmd_compile(_args(tmp_path, "mif"))

    manifest = json.loads((tmp_path / "build" / "real" / "manifest.json").read_text())
    assert {e["name"] for e in manifest} == {
        "add",
        "data",
        "declared",
        "mem",
        "raw",
        "returns",
    }
    mem_entry = next(e for e in manifest if e["name"] == "mem")
    # Golden addresses are relative to the start of RAM.
    assert json.loads((tmp_path / mem_entry["golden"]).read_text()) == {
        "0x00000000": 17,
        "0x00000001": 17,
        "0x00000002": 17,
        "0x00000003": 17,
    }
    # `results` is kept by the linker even though the test never touches it.
    declared_entry = next(e for e in manifest if e["name"] == "declared")
    assert json.loads((tmp_path / declared_entry["golden"]).read_text()) == {
        "0x00000000": 0,
        "0x00000001": 0,
        "0x00000002": 0,
        "0x00000003": 0,
    }
    # The image Spike runs is the test's own program with the Spike
    # stand-in; the image the hardware loads has the routine's fixed address.
    assert (
        _symbols(tmp_path / "build" / "real" / "mem.elf")["rv32_wait_restart"] == 0x100
    )
    spike_elf = _symbols(tmp_path / "build" / "real" / "mem.golden.elf")
    assert spike_elf["rv32_wait_restart"] != 0x100
    assert "tohost" in spike_elf


def test_cmd_spike_run_passes_programs_that_return_from_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(_args(tmp_path, "mif"))

    args = _args(tmp_path, "mif")
    args.only = "add,data,declared,mem,raw,returns"  # type: ignore[attr-defined]
    cmd_spike_run(args)

    out = capsys.readouterr().out
    for name in ("add", "data", "declared", "mem", "raw", "returns"):
        assert f"PASS  {name}" in out


def test_cmd_compile_hex_places_the_image_at_the_flash_base(tmp_path: Path) -> None:
    _make_project(tmp_path)
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    cfg["sim"] = {"hex_format": "verilog"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))

    cmd_compile(_args(tmp_path, "hex"))

    # The first line of an `objcopy -O verilog` file is the address of the
    # first word: the flash base, where the boot ROM jumps to.
    hex_text = (tmp_path / "build" / "sim" / "returns.hex").read_text()
    assert hex_text.startswith("@00000200\n")
