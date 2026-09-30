import argparse
from pathlib import Path
from typing import Any

import pytest
import yaml

from riscv_tools import cli
from riscv_tools.memory_map import (
    check_memory_map,
    evaluate,
    load_platform,
    symbols,
    validate_platform,
)

PLATFORM: dict[str, Any] = {
    "regions": [
        {"name": "BOOT_ROM", "base": "0x0", "size": "2K", "kind": "rom", "exec": True},
        {"name": "FLASH", "base": "0x800", "size": "30K", "kind": "rom", "exec": True},
        {"name": "RAM", "base": "0x8000", "size": "160K", "kind": "ram"},
    ],
    "reserved": {
        "stdout": {"base": "0x2FBE0", "size": "1K+8"},
        "mailbox": {"base": "0x2FFFC", "size": 4},
    },
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "peripherals": [{"name": "GPIO", "base": "0xA0000000", "id": 2}],
    "checks": [
        {
            "name": "config ram base",
            "file": "config.yaml",
            "yaml": "memory.ram_base",
            "expect": "RAM.base",
        },
        {
            "name": "specs ram size",
            "file": "x.specs",
            "pattern": r"--defsym=__ram_size=(\S+)",
            "expect": "RAM.size - (RAM.end - stdout.base)",
        },
        {
            "name": "asm ram end",
            "file": "boot.S",
            "pattern": r"li\s+t0,\s*(0x[0-9A-Fa-f]+)\s*$",
            "expect": "RAM.end",
        },
        {
            "name": "vhdl boot rom size",
            "file": "core.vhd",
            "pattern": r"BOOT_ROM_SIZE_BYTES.*to_unsigned\((16#[0-9A-Fa-f]+#)",
            "expect": "BOOT_ROM.size",
        },
        {
            "name": "ip words",
            "file": "ip.vhd",
            "pattern": r"numwords_a => (\d+)",
            "expect": "RAM.words",
        },
    ],
}

COPIES = {
    "config.yaml": "memory:\n  ram_base: 0x8000\n",
    "x.specs": "*link:\n--defsym=__ram=0x8000 --defsym=__ram_size=160K-1056\n",
    "boot.S": "    li   t0, 0x00030000\n    li   t0, 0x00030000\n",
    "core.vhd": (
        "constant BOOT_ROM_SIZE_BYTES : unsigned := to_unsigned(16#00000800#, 32);\n"
    ),
    "ip.vhd": "numwords_a => 40960,\n",
}


def _project(root: Path, platform: dict[str, Any] | None = None) -> Path:
    for name, text in COPIES.items():
        (root / name).write_text(text)
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(platform or PLATFORM, sort_keys=False))
    return path


def test_evaluate_number_notations() -> None:
    assert evaluate("0x800") == 0x800
    assert evaluate("16#0800#") == 0x800
    assert evaluate("30K") == 30 * 1024
    assert evaluate("0x0002FFFCu") == 0x2FFFC
    assert evaluate("160K-24-1032") == 160 * 1024 - 1056


def test_evaluate_symbols_and_log2() -> None:
    names = {"RAM.words": 40960, "FLASH.words": 7680, "BOOT_ROM.words": 512}
    assert evaluate("RAM.words / 4", names) == 10240
    assert evaluate("log2(BOOT_ROM.words)", names) == 9
    with pytest.raises(ValueError, match="non power of two"):
        evaluate("log2(FLASH.words)", names)
    assert evaluate("clog2(FLASH.words)", names) == 13
    assert evaluate("clog2(BOOT_ROM.words)", names) == 9


def test_evaluate_rejects_unknown_symbol_inexact_division_and_code() -> None:
    with pytest.raises(ValueError, match=r"unknown symbol 'NOPE\.base'"):
        evaluate("NOPE.base")
    with pytest.raises(ValueError, match="inexact division"):
        evaluate("7/2")
    with pytest.raises(ValueError, match="unsupported"):
        evaluate("__import__('os')")


def test_symbols_flattens_regions_reserved_boot_and_peripherals() -> None:
    table = symbols(PLATFORM)
    assert table["RAM.end"] == 0x8000 + 160 * 1024
    assert table["FLASH.words"] == 7680
    assert table["stdout.size"] == 1032
    assert table["boot.wait_restart"] == 0x100
    assert table["GPIO.id"] == 2


def test_the_reference_platform_is_consistent() -> None:
    assert validate_platform(PLATFORM) == []


def _with(**changes: Any) -> dict[str, Any]:
    return {**PLATFORM, **changes}


@pytest.mark.parametrize(
    ("platform", "message"),
    [
        (
            _with(
                regions=[
                    *PLATFORM["regions"],
                    {"name": "X", "base": "0x8000", "size": "1K", "kind": "ram"},
                ]
            ),
            "regions RAM and X overlap",
        ),
        (
            _with(reserved={"w": {"base": "0x100", "size": 4}}),
            "reserved w",
        ),
        (
            _with(
                reserved={
                    "a": {"base": "0x2FFF0", "size": 8},
                    "b": {"base": "0x2FFF4", "size": 8},
                }
            ),
            "reserved a and b overlap",
        ),
        (_with(boot={"entry": "0x8000"}), "boot.entry"),
        (_with(boot={"wait_restart": "0x900"}), "boot.wait_restart"),
        (
            _with(peripherals=[{"name": "GPIO", "base": "0x90000000", "id": 2}]),
            "peripheral GPIO base",
        ),
    ],
)
def test_validate_platform_reports_an_inconsistent_map(
    platform: dict[str, Any], message: str
) -> None:
    problems = validate_platform(platform)
    assert any(message in str(p) for p in problems), problems


def test_check_passes_when_every_copy_agrees(tmp_path: Path) -> None:
    count, problems = check_memory_map(_project(tmp_path), tmp_path)
    assert (count, problems) == (5, [])


@pytest.mark.parametrize(
    ("file", "old", "new", "check"),
    [
        ("config.yaml", "0x8000", "0x9000", "config ram base"),
        ("x.specs", "160K-1056", "160K-1040", "specs ram size"),
        (
            "boot.S",
            "0x00030000\n    li   t0, 0x00030000",
            "0x00030000\n    li   t0, 0x00038000",
            "asm ram end",
        ),
        ("core.vhd", "16#00000800#", "16#00001000#", "vhdl boot rom size"),
        ("ip.vhd", "40960", "32768", "ip words"),
    ],
)
def test_check_fails_when_one_copy_diverges(
    tmp_path: Path, file: str, old: str, new: str, check: str
) -> None:
    path = _project(tmp_path)
    (tmp_path / file).write_text(COPIES[file].replace(old, new))
    _, problems = check_memory_map(path, tmp_path)
    assert [p.check for p in problems] == [check]


def test_check_reports_every_divergent_match_of_one_pattern(tmp_path: Path) -> None:
    path = _project(tmp_path)
    (tmp_path / "boot.S").write_text(
        "    li   t0, 0x00038000\n    li   t0, 0x00038000\n"
    )
    _, problems = check_memory_map(path, tmp_path)
    assert len(problems) == 2


def test_check_fails_when_a_copy_no_longer_matches_the_pattern(tmp_path: Path) -> None:
    path = _project(tmp_path)
    (tmp_path / "ip.vhd").write_text("numwords_a=>40960\n")
    _, problems = check_memory_map(path, tmp_path)
    assert "nothing matched" in str(problems[0])


def test_check_fails_on_a_missing_file_unless_optional(tmp_path: Path) -> None:
    path = _project(tmp_path)
    (tmp_path / "ip.vhd").unlink()
    _, problems = check_memory_map(path, tmp_path)
    assert "file not found" in str(problems[0])

    platform = yaml.safe_load(path.read_text())
    platform["checks"][-1]["optional"] = True
    path.write_text(yaml.safe_dump(platform))
    assert check_memory_map(path, tmp_path)[1] == []


def test_check_stops_at_an_inconsistent_map(tmp_path: Path) -> None:
    platform = _with(boot={"entry": "0x8000"})
    count, problems = check_memory_map(_project(tmp_path, platform), tmp_path)
    assert count == 0
    assert "boot.entry" in str(problems[0])


def test_load_platform_rejects_a_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "p.yaml"
    path.write_text("- 1\n")
    with pytest.raises(ValueError, match="not a YAML mapping"):
        load_platform(path)


def test_cmd_check_memory_map_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path)
    args = argparse.Namespace(root=str(tmp_path), platform="platform.yaml")
    cli.cmd_check_memory_map(args)
    assert "memory map OK: 5 checks" in capsys.readouterr().out

    (tmp_path / "ip.vhd").write_text("numwords_a => 1,\n")
    with pytest.raises(SystemExit) as exc:
        cli.cmd_check_memory_map(args)
    assert exc.value.code == 1
    assert "MISMATCH ip words" in capsys.readouterr().err
