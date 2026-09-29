import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from riscv_tools import run_log

# _discover_tests is private, but the discovery/sorting behavior it
# implements is worth testing directly, without a real toolchain.
from riscv_tools.cli import (
    _discover_tests,  # pyright: ignore[reportPrivateUsage]
    cmd_compile,
    cmd_spike_run,
)

GCC = "riscv32-unknown-elf-gcc"
SPIKE = "spike"


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
        "volatile unsigned int results[1];\n"
        "int main(void) {\n"
        "    results[0] = 0x11111111u;\n"
        "    RV32_PASS();\n"
        "    return 0;\n"
        "}\n"
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
        "    la sp, _stack_top\n"
        "    call main\n"
        "rv32_wait_restart:\n"
        "    li t0, 1\n"
        "    la t1, tohost\n"
        "    sw t0, 0(t1)\n"
        "1:  j 1b\n"
        '.section .tohost,"aw",@nobits\n'
        ".balign 8\n"
        ".globl tohost\n"
        "tohost: .space 8\n"
        ".globl fromhost\n"
        "fromhost: .space 8\n"
    )
    (root / "link.ld").write_text(
        "ENTRY(_start)\n"
        "SECTIONS {\n"
        "    . = 0x00000000;\n"
        "    .text : { *(.text*) }\n"
        "    .data : { *(.data*) }\n"
        "    . = 0x8000;\n"
        "    .bss : { *(.bss*) *(COMMON) }\n"
        "    .tohost (NOLOAD) : { *(.tohost) }\n"
        "    _stack_top = 0x9000;\n"
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
                "memory": {
                    "rom_base": 0,
                    "rom_words": 8192,
                    "ram_base": 0x8000,
                    "ram_words": 1024,
                },
            }
        )
    )


def _no_log(*_args: object, **_kwargs: object) -> None:
    return None


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


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_compile_mif_builds_every_kind(tmp_path: Path) -> None:
    _make_project(tmp_path)

    cmd_compile(_args(tmp_path, "mif"))

    manifest = json.loads((tmp_path / "build" / "real" / "manifest.json").read_text())
    assert {e["name"] for e in manifest} == {"add", "mem", "raw"}
    mem_entry = next(e for e in manifest if e["name"] == "mem")
    assert mem_entry["kind"] == "memory"
    golden_path = tmp_path / mem_entry["golden"]
    assert json.loads(golden_path.read_text()) == {
        "0x00000000": 17,
        "0x00000001": 17,
        "0x00000002": 17,
        "0x00000003": 17,
    }


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_compile_hex_builds_every_kind(tmp_path: Path) -> None:
    _make_project(tmp_path)

    cmd_compile(_args(tmp_path, "hex"))

    manifest = json.loads((tmp_path / "build" / "sim" / "manifest.json").read_text())
    assert {e["name"] for e in manifest} == {"add", "mem", "raw"}
    mem_entry = next(e for e in manifest if e["name"] == "mem")
    assert mem_entry["kind"] == "memory"
    assert mem_entry["hex"].endswith("mem.hex")
    assert (tmp_path / mem_entry["golden"]).is_file()


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_spike_run_passes_compiled_tests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_log.start redirects the process's stdout into a log tee, which
    # pytest's own capture can't coexist with.
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(_args(tmp_path, "mif"))

    args = _args(tmp_path, "mif")
    args.only = "add,mem"  # type: ignore[attr-defined]
    cmd_spike_run(args)

    out = capsys.readouterr().out
    assert "PASS  add" in out
    assert "PASS  mem" in out


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_spike_run_rejects_a_test_missing_from_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(_args(tmp_path, "mif"))

    args = _args(tmp_path, "mif")
    args.only = "nope"  # type: ignore[attr-defined]
    with pytest.raises(SystemExit):
        cmd_spike_run(args)
