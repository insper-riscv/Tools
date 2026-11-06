"""Tests for the interrupt wiring generated from the platform."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import MAP_REGIONS, MAP_RESERVED, check_in, check_not_in

from riscv_tools.memory_map import render_all, set_override

PLATFORM: dict[str, Any] = {
    "profile": "rv32i_zicsr",
    "profiles": "matrix.yaml",
    "extras": ["Interrupts"],
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "peripherals": [
        {"name": "CLINT", "base": "0xE0000000", "id": 6},
        {"name": "EXT_IRQ", "base": "0xF0000000", "id": 7},
    ],
    "interrupts": {"clock_hz": 50000000, "mtime_hz": 1000000},
    "generate": {
        "runtime": {"path": "gen/rv32.h", "ram": "RAM"},
        "vhdl": {
            "path": "gen/irq_pkg.vhd",
            "package": "irq_pkg",
            "rom": "FLASH",
            "ram": "RAM",
            "ext_base": "0x80000000",
        },
    },
}


def _write(base: Path, **changes: Any) -> Path:
    """Write the matrix and a platform with `changes` applied."""
    spec = {
        "bases": [{"name": "rv32i", "generics": {"num_regs": 32}}],
        "extensions": [{"name": "Zicsr", "generic": "has_zicsr"}],
    }
    (base / "matrix.yaml").write_text(yaml.safe_dump(spec))
    platform = yaml.safe_load(yaml.safe_dump(PLATFORM)) | changes
    path = base / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    set_override(None)
    return path


def test_the_package_has_the_tick_and_the_switch(tmp_path: Path) -> None:
    """The VHDL package carries the rates and `HAS_INTERRUPTS`."""
    text = render_all(_write(tmp_path), tmp_path)[tmp_path / "gen/irq_pkg.vhd"]
    check_in("constant HAS_INTERRUPTS      : boolean  := true;", text)
    check_in("constant CLOCK_HZ          : positive := 50000000;", text)
    check_in("constant MTIME_HZ          : positive := 1000000;", text)
    check_in("constant CLINT_TICK_CYCLES : positive := 50;", text)
    check_in("constant CLINT_BASE : std_logic_vector(31 downto 0)", text)
    check_in("constant EXT_IRQ_ID   : natural := 7;", text)


@pytest.mark.parametrize(
    ("macro", "value"),
    [
        ("RV32_CLINT_BASE", "0xE0000000"),
        ("RV32_MSIP", "0xE0000000"),
        ("RV32_MTIMECMP", "0xE0004000"),
        ("RV32_MTIME", "0xE000BFF8"),
        ("RV32_MTIME_HZ", "0x000F4240"),
    ],
)
def test_the_header_has_the_registers_of_the_clint(
    tmp_path: Path, macro: str, value: str
) -> None:
    """The runtime header has the registers and the tick rate."""
    files = render_all(_write(tmp_path), tmp_path)
    check_in(
        f"#define {macro} RV32_ADDRESS({value})",
        files[tmp_path / "gen/rv32.h"],
    )


def test_without_the_section_nothing_is_added(tmp_path: Path) -> None:
    """Without `interrupts` there are no constants and no macros."""
    path = _write(tmp_path, interrupts=None, extras=[])
    files = render_all(path, tmp_path)
    check_not_in("MTIME_HZ", files[tmp_path / "gen/irq_pkg.vhd"])
    check_not_in("RV32_MTIME", files[tmp_path / "gen/rv32.h"])


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"interrupts": {"clock_hz": 50000000}}, "mtime_hz is missing"),
        (
            {"interrupts": {"clock_hz": 50000000, "mtime_hz": 3000000}},
            "not a multiple",
        ),
        ({"peripherals": []}, "no CLINT"),
        ({"extras": []}, "does not turn on has_interrupts"),
    ],
)
def test_an_inconsistent_section_is_rejected(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    """Each way the section disagrees with the platform is an error."""
    with pytest.raises(ValueError, match=message):
        render_all(_write(tmp_path, **changes), tmp_path)
