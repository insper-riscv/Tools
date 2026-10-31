"""Tests for cli_compile."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    C_ADD_SOURCE,
    C_MEM_SOURCE,
    compile_args,
    toolchain_section,
    write_c_test,
    write_config,
    write_rv32_header,
)

from riscv_tools import run_log
from riscv_tools.cli import (
    cmd_compile,
    cmd_spike_run,
    discover_tests,
)

GCC = "riscv32-unknown-elf-gcc"
SPIKE = "spike"


def _make_project(root: Path) -> None:
    write_c_test(root, "add", C_ADD_SOURCE)
    write_c_test(root, "mem", C_MEM_SOURCE)

    (root / "asm" / "raw").mkdir(parents=True)
    (root / "asm" / "raw" / "src.S").write_text(
        ".section .text\n.globl main\nmain:\n    jal x0, main\n"
    )

    write_rv32_header(root, 0x00003FF0)
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

    write_config(
        root,
        {
            "toolchain": toolchain_section(),
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
        },
    )


def _no_log(*_args: object, **_kwargs: object) -> None:
    return None


def _cfg_dict(root: Path) -> dict[str, Any]:
    return yaml.safe_load((root / "config.yaml").read_text())


def test_discover_tests_finds_c_and_asm_sorted_by_name(tmp_path: Path) -> None:
    """Discover tests finds c and asm sorted by name."""
    _make_project(tmp_path)

    sources = discover_tests(tmp_path, _cfg_dict(tmp_path))

    assert [s.parent.name for s in sources] == ["add", "mem", "raw"]
    assert sources[0].name == "src.c"
    assert sources[2].name == "src.S"


def test_discover_tests_empty_when_no_folders(tmp_path: Path) -> None:
    """Discover tests empty when no folders."""
    (tmp_path / "c").mkdir()
    (tmp_path / "asm").mkdir()
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"paths": {"c_dir": "c", "asm_dir": "asm"}})
    )

    assert discover_tests(tmp_path, _cfg_dict(tmp_path)) == []


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_compile_mif_builds_every_kind(tmp_path: Path) -> None:
    """Cmd compile mif builds every kind."""
    _make_project(tmp_path)

    cmd_compile(compile_args(tmp_path, "mif"))

    manifest = json.loads(
        (tmp_path / "build" / "real" / "manifest.json").read_text()
    )
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
    """Cmd compile hex builds every kind."""
    _make_project(tmp_path)

    cmd_compile(compile_args(tmp_path, "hex"))

    manifest = json.loads(
        (tmp_path / "build" / "sim" / "manifest.json").read_text()
    )
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
    """Cmd spike run passes compiled tests."""
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(compile_args(tmp_path, "mif"))

    args = compile_args(tmp_path, "mif", only="add,mem")
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
    """Cmd spike run rejects a test missing from the manifest."""
    monkeypatch.setattr(run_log, "start", _no_log)
    _make_project(tmp_path)
    cmd_compile(compile_args(tmp_path, "mif"))

    args = compile_args(tmp_path, "mif", only="nope")
    with pytest.raises(SystemExit):
        cmd_spike_run(args)


@pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(SPIKE) is None,
    reason=f"needs {GCC} and {SPIKE} on PATH",
)
def test_cmd_compile_hex_uses_the_verilog_format_when_configured(
    tmp_path: Path,
) -> None:
    """Cmd compile hex uses the verilog format when configured."""
    _make_project(tmp_path)
    cfg = _cfg_dict(tmp_path)
    cfg["sim"] = {"hex_format": "verilog"}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))

    cmd_compile(compile_args(tmp_path, "hex"))

    hex_text = (tmp_path / "build" / "sim" / "add.hex").read_text()
    assert hex_text.startswith("@00000000\n")
