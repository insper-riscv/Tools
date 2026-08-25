import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

# _discover_tests is private, but the discovery/sorting behavior it
# implements is worth testing directly, without a real toolchain.
from riscv_tools.cli import (
    _discover_tests,  # pyright: ignore[reportPrivateUsage]
    cmd_compile,
)

GCC = "riscv32-unknown-elf-gcc"


def _make_project(root: Path) -> None:
    (root / "c" / "add").mkdir(parents=True)
    (root / "c" / "add" / "src.c").write_text(
        '#include "rv32_test.h"\n'
        "int main(void) {\n"
        "    if (6 * 7 == 42) { RV32_PASS(); }\n"
        "    RV32_FAIL();\n"
        "    return 0;\n"
        "}\n"
    )

    (root / "c" / "mem").mkdir(parents=True)
    (root / "c" / "mem" / "src.c").write_text(
        "// RV32_TEST_KIND: memory\n"
        '#include "rv32_test.h"\n'
        "static volatile unsigned int *const BUF = (volatile unsigned int *)0x10;\n"
        "int main(void) {\n"
        "    BUF[0] = 0x11111111u;\n"
        "    RV32_PASS();\n"
        "    return 0;\n"
        "}\n"
    )
    (root / "c" / "mem" / "manifest.json").write_text(
        '{"0x00000010": 17, "0x00000011": 17, "0x00000012": 17, "0x00000013": 17}\n'
    )

    (root / "asm" / "raw").mkdir(parents=True)
    (root / "asm" / "raw" / "src.S").write_text(
        ".section .text\n.globl main\nmain:\n    jal x0, main\n"
    )

    include_dir = root / "include"
    include_dir.mkdir()
    (include_dir / "rv32_test.h").write_text(
        "#define RV32_MAILBOX_ADDR ((volatile unsigned int *)0x00003FFC)\n"
        "extern void rv32_wait_restart(void) __attribute__((noreturn));\n"
        "static inline void RV32_PASS(void) { *RV32_MAILBOX_ADDR = 1; "
        "rv32_wait_restart(); }\n"
        "static inline void RV32_FAIL(void) { *RV32_MAILBOX_ADDR = 2; "
        "rv32_wait_restart(); }\n"
    )
    (root / "crt0.S").write_text(
        ".section .text\n"
        ".globl _start\n"
        ".globl rv32_wait_restart\n"
        "_start:\n"
        "    call main\n"
        "rv32_wait_restart:\n"
        "    j rv32_wait_restart\n"
    )
    (root / "link.ld").write_text(
        "ENTRY(_start)\n"
        "SECTIONS {\n"
        "    . = 0x00000000;\n"
        "    .text : { *(.text*) }\n"
        "    .data : { *(.data*) }\n"
        "    .bss : { *(.bss*) }\n"
        "}\n"
    )

    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "toolchain": {"gcc": GCC, "objcopy": "riscv32-unknown-elf-objcopy"},
                "isa": {
                    "base": "i",
                    "default_ext": "",
                    "canonical_order": "MAFDQLCBJTPVNH",
                },
                "paths": {
                    "include_dir": "include",
                    "crt0": "crt0.S",
                    "linker_script": "link.ld",
                    "build_dir": "build",
                    "c_dir": "c",
                    "asm_dir": "asm",
                },
                "quartus": {"default_timeout_s": 5},
                "memory": {"rom_words": 8192},
            }
        )
    )


def _cfg_dict(root: Path) -> dict[str, Any]:
    return yaml.safe_load((root / "config.yaml").read_text())


def _args(root: Path, emit: str) -> Any:
    class _Args:
        config = str(root / "config.yaml")
        root_ = str(root)
        manifest = None
        manifest_per_test = None

    args = _Args()
    args.root = str(root)  # type: ignore[attr-defined]
    args.emit = emit  # type: ignore[attr-defined]
    return args


def test_discover_tests_finds_c_and_asm_sorted_by_name(tmp_path: Path) -> None:
    _make_project(tmp_path)

    sources = _discover_tests(tmp_path, _cfg_dict(tmp_path))

    assert [s.parent.name for s in sources] == ["add", "mem", "raw"]
    assert sources[0].name == "src.c"
    assert sources[2].name == "src.S"


def test_discover_tests_empty_when_no_folders(tmp_path: Path) -> None:
    (tmp_path / "c").mkdir()
    (tmp_path / "asm").mkdir()
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"paths": {"c_dir": "c", "asm_dir": "asm"}})
    )

    assert _discover_tests(tmp_path, _cfg_dict(tmp_path)) == []


@pytest.mark.skipif(shutil.which(GCC) is None, reason=f"needs {GCC} on PATH")
def test_cmd_compile_mif_builds_every_kind(tmp_path: Path) -> None:
    _make_project(tmp_path)

    cmd_compile(_args(tmp_path, "mif"))

    manifest = json.loads((tmp_path / "build" / "real" / "manifest.json").read_text())
    assert {e["name"] for e in manifest} == {"add", "mem", "raw"}
    mem_entry = next(e for e in manifest if e["name"] == "mem")
    assert mem_entry["kind"] == "memory"
    assert mem_entry["golden"] == "c/mem/manifest.json"


@pytest.mark.skipif(shutil.which(GCC) is None, reason=f"needs {GCC} on PATH")
def test_cmd_compile_hex_skips_memory_kind(tmp_path: Path) -> None:
    _make_project(tmp_path)

    cmd_compile(_args(tmp_path, "hex"))

    manifest = json.loads((tmp_path / "build" / "sim" / "manifest.json").read_text())
    assert {e["name"] for e in manifest} == {"add", "raw"}
