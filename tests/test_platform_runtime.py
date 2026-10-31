"""End-to-end tests of the picolibc runtime (no crt0 or linker).

The project under test (fixtures/platform_min/) describes its platform
in a GCC specs file and supplies only `_exit`, the boot ROM and a Spike
stand-in. The tests prove that programs compile and link with nothing
else, that a program can return from main, that Spike generates the
goldens from the image the hardware loads, and that the image starts
where the boot ROM jumps.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from support import (
    C_ADD_SOURCE,
    C_MEM_SOURCE,
    GCC,
    ISA,
    compile_args,
    has_picolibc,
    toolchain_section,
    write_c_test,
    write_config,
    write_rv32_header,
)

from riscv_tools import run_log
from riscv_tools.cli import cmd_compile, cmd_spike_run
from riscv_tools.compiler import BuildSetup, LinkSetup, compile_test

NM = "riscv32-unknown-elf-nm"
SPIKE = "spike"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "platform_min"


pytestmark = pytest.mark.skipif(
    not has_picolibc() or shutil.which(SPIKE) is None,
    reason=f"needs a {GCC} configured with picolibc, and {SPIKE}",
)


def _make_project(root: Path) -> None:
    shutil.copytree(FIXTURE, root / "platform")

    write_c_test(root, "add", C_ADD_SOURCE)
    write_c_test(root, "mem", C_MEM_SOURCE)

    # A `results` too big for the small-data section, so it lands in
    # .bss after the platform's own objects: the address the golden
    # holds must still be the one in the image the hardware loads.
    write_c_test(
        root,
        "wide",
        "// RV32_TEST_KIND: memory\n"
        '#include "rv32_test.h"\n'
        "volatile unsigned int results[8];\n"
        "int main(void) {\n"
        "    for (int i = 0; i < 8; i++) { results[i] = i + 1; }\n"
        "    RV32_PASS();\n"
        "}\n",
    )

    # Declares `results` and never touches it: the linker must still
    # keep it, since the golden is read from it.
    write_c_test(
        root,
        "declared",
        "// RV32_TEST_KIND: memory\n"
        '#include "rv32_test.h"\n'
        "volatile unsigned int results[1];\n"
        "int main(void) { RV32_PASS(); }\n",
    )

    # Returns from main, as any C program does: the crt0 calls exit().
    write_c_test(
        root,
        "returns",
        "int main(void) { return 0; }\n",
    )

    # Initialized data, zero data and a constant: what the crt0 must
    # copy, clear and leave alone. A wrong value returns nonzero, which
    # _exit reports as FAIL.
    write_c_test(
        root,
        "data",
        'char text[7] = "abcdef";\n'
        "int word = 0x12345678;\n"
        "int zero;\n"
        "const int table[2] = {0x0BADF00D, 0x1234};\n"
        "volatile int selector = 1;\n"
        "int main(void) {\n"
        "    if (text[5] != 'f' || text[6] != 0) return 1;\n"
        "    if (word != 0x12345678) return 2;\n"
        "    if (zero != 0) return 3;\n"
        "    if (table[0] != 0x0BADF00D || table[selector] != 0x1234)"
        " return 4;\n"
        "    return 0;\n"
        "}\n",
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

    write_rv32_header(root, 0x0002FFFC)

    write_config(
        root,
        {
            "toolchain": toolchain_section(specs="platform/rv32im-fpga.specs"),
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
        },
    )


def _no_log(*_args: object, **_kwargs: object) -> None:
    return None


def _symbols(elf: Path) -> dict[str, int]:
    out = subprocess.run(
        [NM, str(elf)], check=True, capture_output=True, text=True
    )
    return {
        line.split()[2]: int(line.split()[0], 16)
        for line in out.stdout.splitlines()
    }


def test_compile_needs_no_crt0_or_linker_script(tmp_path: Path) -> None:
    """Compile needs no crt0 or linker script."""
    src = tmp_path / "src.c"
    src.write_text(
        "#include <string.h>\n"
        'int main(void) { return strlen("riscv") != 5; }\n'
    )

    setup = BuildSetup(
        toolchain_cfg={
            "gcc": GCC,
            "objcopy": "riscv32-unknown-elf-objcopy",
            "specs": str(FIXTURE / "rv32im-fpga.specs"),
        },
        isa_cfg=ISA,
        default_timeout_s=5.0,
        include_dir=tmp_path,
        link=LinkSetup(extra_sources=[FIXTURE / "_exit.c"]),
    )
    bin_, _march, _kind, _timeout = compile_test(
        setup, src, "strlen", tmp_path / "build"
    )

    syms = _symbols(tmp_path / "build" / "strlen.elf")
    assert bin_.is_file()
    # The toolchain's crt0 starts at the flash base the specs file
    # gives.
    assert syms["_start"] == 0x800
    # The boot ROM's routine is at its fixed address, from the specs
    # file.
    assert syms["rv32_wait_restart"] == 0x100


def test_cmd_compile_builds_every_kind_and_the_goldens(tmp_path: Path) -> None:
    """Cmd compile builds every kind and the goldens."""
    _make_project(tmp_path)

    cmd_compile(compile_args(tmp_path, "mif"))

    manifest = json.loads(
        (tmp_path / "build" / "real" / "manifest.json").read_text()
    )
    assert {e["name"] for e in manifest} == {
        "add",
        "data",
        "declared",
        "mem",
        "raw",
        "returns",
        "wide",
    }
    mem_entry = next(e for e in manifest if e["name"] == "mem")
    # Golden addresses are relative to the start of RAM.
    assert json.loads((tmp_path / mem_entry["golden"]).read_text()) == {
        "0x00000000": 17,
        "0x00000001": 17,
        "0x00000002": 17,
        "0x00000003": 17,
    }
    # `results` is kept by the linker even though the test never touches
    # it.
    declared_entry = next(e for e in manifest if e["name"] == "declared")
    assert json.loads((tmp_path / declared_entry["golden"]).read_text()) == {
        "0x00000000": 0,
        "0x00000001": 0,
        "0x00000002": 0,
        "0x00000003": 0,
    }
    # The image Spike runs is the test's own program with the Spike
    # stand-in; the image the hardware loads has the routine's fixed
    # address.
    assert (
        _symbols(tmp_path / "build" / "real" / "mem.elf")["rv32_wait_restart"]
        == 0x100
    )
    spike_elf = _symbols(tmp_path / "build" / "real" / "mem.golden.elf")
    assert spike_elf["rv32_wait_restart"] != 0x100
    assert "tohost" in spike_elf
    # The stand-in takes no space: a variable has the same address in
    # both images, so the golden's addresses are the hardware image's.
    for name in ("mem", "wide", "declared"):
        hardware = _symbols(tmp_path / "build" / "real" / f"{name}.elf")
        spike = _symbols(tmp_path / "build" / "real" / f"{name}.golden.elf")
        assert hardware["results"] == spike["results"], name


def test_cmd_spike_run_passes_programs_that_return_from_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cmd spike run passes programs that return from main."""
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(compile_args(tmp_path, "mif"))

    args = compile_args(
        tmp_path, "mif", only="add,data,declared,mem,raw,returns,wide"
    )
    cmd_spike_run(args)

    out = capsys.readouterr().out
    for name in ("add", "data", "declared", "mem", "raw", "returns", "wide"):
        assert f"PASS  {name}" in out


def test_cmd_compile_hex_places_the_image_at_the_flash_base(
    tmp_path: Path,
) -> None:
    """Cmd compile hex places the image at the flash base."""
    _make_project(tmp_path)
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    cfg["sim"] = {"hex_format": "verilog"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))

    cmd_compile(compile_args(tmp_path, "hex"))

    # The first line of an `objcopy -O verilog` file is the address of
    # the first word: the flash base, where the boot ROM jumps to.
    hex_text = (tmp_path / "build" / "sim" / "returns.hex").read_text()
    assert hex_text.startswith("@00000200\n")
