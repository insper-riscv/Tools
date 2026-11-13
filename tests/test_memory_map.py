"""Tests for memory_map."""

import argparse
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check, check_equal, check_in

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
        {
            "name": "BOOT_MEMORY",
            "base": "0x0",
            "size": "2K",
            "kind": "rom",
            "exec": True,
        },
        {
            "name": "FLASH",
            "base": "0x800",
            "size": "30K",
            "kind": "rom",
            "exec": True,
        },
        {"name": "RAM", "base": "0x8000", "size": "160K", "kind": "ram"},
    ],
    "reserved": {
        "stdout": {"base": "0x2FBE0", "size": "1K+8"},
        "last_word": {"base": "0x2FFFC", "size": 4},
    },
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "peripherals": [{"name": "GPIO", "base": "0xA0000000", "size": "16"}],
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
            "name": "vhdl boot memory size",
            "file": "core.vhd",
            "pattern": (
                r"BOOT_MEMORY_SIZE_BYTES.*to_unsigned\((16#[0-9A-Fa-f]+#)"
            ),
            "expect": "BOOT_MEMORY.size",
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
        "constant BOOT_MEMORY_SIZE_BYTES : unsigned := "
        "to_unsigned(16#00000800#, 32);\n"
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
    """Evaluate number notations."""
    check_equal(evaluate("0x800"), 0x800)
    check_equal(evaluate("16#0800#"), 0x800)
    check_equal(evaluate("30K"), 30 * 1024)
    check_equal(evaluate("0x0002FFFCu"), 0x2FFFC)
    check_equal(evaluate("160K-24-1032"), 160 * 1024 - 1056)


def test_evaluate_symbols_and_log2() -> None:
    """Evaluate symbols and log2."""
    names = {"RAM.words": 40960, "FLASH.words": 7680, "BOOT_MEMORY.words": 512}
    check_equal(evaluate("RAM.words / 4", names), 10240)
    check_equal(evaluate("log2(BOOT_MEMORY.words)", names), 9)
    with pytest.raises(ValueError, match="non power of two"):
        evaluate("log2(FLASH.words)", names)
    check_equal(evaluate("clog2(FLASH.words)", names), 13)
    check_equal(evaluate("clog2(BOOT_MEMORY.words)", names), 9)


def test_evaluate_rejects_unknown_symbol_inexact_division_and_code() -> None:
    """Evaluate rejects unknown symbol inexact division and code."""
    with pytest.raises(ValueError, match=r"unknown symbol 'NOPE\.base'"):
        evaluate("NOPE.base")
    with pytest.raises(ValueError, match="inexact division"):
        evaluate("7/2")
    with pytest.raises(ValueError, match="unsupported"):
        evaluate("__import__('os')")


def test_symbols_flattens_regions_reserved_boot_and_peripherals() -> None:
    """Symbols flattens regions reserved boot and peripherals."""
    table = symbols(PLATFORM)
    check_equal(table["RAM.end"], 0x8000 + 160 * 1024)
    check_equal(table["FLASH.words"], 7680)
    check_equal(table["stdout.size"], 1032)
    check_equal(table["boot.wait_restart"], 0x100)
    check_equal(table["GPIO.index"], 0)
    check_equal(table["GPIO.size"], 16)
    check_equal(table["GPIO.window"], 16)


def test_the_reference_platform_is_consistent() -> None:
    """The reference platform is consistent."""
    check_equal(validate_platform(PLATFORM), [])


def _with(**changes: Any) -> dict[str, Any]:
    return {**PLATFORM, **changes}


@pytest.mark.parametrize(
    ("platform", "message"),
    [
        (
            _with(
                regions=[
                    *PLATFORM["regions"],
                    {
                        "name": "X",
                        "base": "0x8000",
                        "size": "1K",
                        "kind": "ram",
                    },
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
            _with(
                peripherals=[
                    {"name": "GPIO", "base": "0x90000008", "size": "16"}
                ]
            ),
            "V-P2 peripheral GPIO base",
        ),
    ],
)
def test_validate_platform_reports_an_inconsistent_map(
    platform: dict[str, Any], message: str
) -> None:
    """Validate platform reports an inconsistent map."""
    problems = validate_platform(platform)
    check(any(message in str(p) for p in problems), str(problems))


def test_check_passes_when_every_copy_agrees(tmp_path: Path) -> None:
    """Check passes when every copy agrees."""
    count, problems = check_memory_map(_project(tmp_path), tmp_path)
    check_equal(count, 5)
    check_equal(problems, [])


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
        ("core.vhd", "16#00000800#", "16#00001000#", "vhdl boot memory size"),
        ("ip.vhd", "40960", "32768", "ip words"),
    ],
)
def test_check_fails_when_one_copy_diverges(
    tmp_path: Path, file: str, old: str, new: str, check: str
) -> None:
    """Check fails when one copy diverges."""
    path = _project(tmp_path)
    (tmp_path / file).write_text(COPIES[file].replace(old, new))
    _, problems = check_memory_map(path, tmp_path)
    check_equal([p.check for p in problems], [check])


def test_check_reports_every_divergent_match_of_one_pattern(
    tmp_path: Path,
) -> None:
    """Check reports every divergent match of one pattern."""
    path = _project(tmp_path)
    (tmp_path / "boot.S").write_text(
        "    li   t0, 0x00038000\n    li   t0, 0x00038000\n"
    )
    _, problems = check_memory_map(path, tmp_path)
    check_equal(len(problems), 2)


def test_check_fails_when_a_copy_no_longer_matches_the_pattern(
    tmp_path: Path,
) -> None:
    """Check fails when a copy no longer matches the pattern."""
    path = _project(tmp_path)
    (tmp_path / "ip.vhd").write_text("numwords_a=>40960\n")
    _, problems = check_memory_map(path, tmp_path)
    check_in("nothing matched", str(problems[0]))


def test_check_fails_on_a_missing_file_unless_optional(tmp_path: Path) -> None:
    """Check fails on a missing file unless optional."""
    path = _project(tmp_path)
    (tmp_path / "ip.vhd").unlink()
    _, problems = check_memory_map(path, tmp_path)
    check_in("file not found", str(problems[0]))

    platform = yaml.safe_load(path.read_text())
    platform["checks"][-1]["optional"] = True
    path.write_text(yaml.safe_dump(platform))
    check_equal(check_memory_map(path, tmp_path)[1], [])


def test_check_stops_at_an_inconsistent_map(tmp_path: Path) -> None:
    """Check stops at an inconsistent map."""
    platform = _with(boot={"entry": "0x8000"})
    count, problems = check_memory_map(_project(tmp_path, platform), tmp_path)
    check_equal(count, 0)
    check_in("boot.entry", str(problems[0]))


def test_load_platform_rejects_a_non_mapping(tmp_path: Path) -> None:
    """Load platform rejects a non mapping."""
    path = tmp_path / "p.yaml"
    path.write_text("- 1\n")
    with pytest.raises(ValueError, match="not a YAML mapping"):
        load_platform(path)


def test_cmd_check_memory_map_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cmd check memory map exit status."""
    _project(tmp_path)
    args = argparse.Namespace(
        root=str(tmp_path),
        platform="platform.yaml",
        accept_inferred_pins=False,
    )
    cli.cmd_check_memory_map(args)
    check_in("memory map OK: 5 checks", capsys.readouterr().out)

    (tmp_path / "ip.vhd").write_text("numwords_a => 1,\n")
    with pytest.raises(SystemExit) as exc:
        cli.cmd_check_memory_map(args)
    check_equal(exc.value.code, 1)
    check_in("MISMATCH ip words", capsys.readouterr().err)


def test_a_negative_offset_is_reported_with_its_sign(tmp_path: Path) -> None:
    """A negative offset is reported with its sign."""
    platform = _with(
        checks=[
            {
                "name": "offset",
                "file": "off.S",
                "pattern": r"(-\d+)\(t0\)",
                "expect": "last_word.base - RAM.end",
            }
        ]
    )
    path = _project(tmp_path, platform)
    (tmp_path / "off.S").write_text("sw x0, -12(t0)\n")
    _, problems = check_memory_map(path, tmp_path)
    check_in(
        "found -12 (-0xC), expected last_word.base - RAM.end (-0x4)",
        str(problems[0]),
    )
