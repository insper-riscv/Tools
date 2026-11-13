"""Tests for the clocks of the platform used by the memory map."""

from pathlib import Path
from typing import Any

import pytest
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_in,
    check_not_in,
    write_zicsr_platform,
)

from riscv_tools.memory_map import render_all
from riscv_tools.memory_map.checks import check_memory_map

PLATFORM: dict[str, Any] = {
    "profile": "rv32i_zicsr",
    "profiles": "matrix.yaml",
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "clocks": {
        "core": {"mhz": 76.923077, "phase_ps": 7500},
        "mem": {"mhz": 100},
    },
    "generate": {
        "runtime": {"path": "gen/rv32.h", "ram": "RAM"},
        "vhdl": {
            "path": "gen/clk_pkg.vhd",
            "package": "clk_pkg",
            "rom": "FLASH",
            "ram": "RAM",
        },
    },
}

PLL = '.output_clock_frequency0("100.000000 MHz"),\n'


def _write(base: Path, **changes: Any) -> Path:
    """Write the matrix and a platform with `changes` applied."""
    return write_zicsr_platform(base, PLATFORM, **changes)


def test_the_package_has_the_clock_and_the_period(tmp_path: Path) -> None:
    """The VHDL package carries the rate and the period in ps."""
    text = render_all(_write(tmp_path), tmp_path)[tmp_path / "gen/clk_pkg.vhd"]
    check_in("constant SDRAM_CLOCK_HZ : positive := 100000000;", text)
    check_in("constant SDRAM_TCK_PS   : positive := 10000;", text)


def test_without_the_section_nothing_is_added(tmp_path: Path) -> None:
    """Without `clocks.mem` there are no constants."""
    files = render_all(_write(tmp_path, clocks=None), tmp_path)
    check_not_in("SDRAM_TCK_PS", files[tmp_path / "gen/clk_pkg.vhd"])


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"mem": {}}, "mem.mhz is missing"),
        ({"mem": {"mhz": 0}}, "mem.mhz is missing or not positive"),
        ({"mem": {"mhz": 3000000}}, "no whole period"),
        ({"mem": {"mhz": 99.9999999}}, "no whole period"),
    ],
)
def test_an_inconsistent_section_is_rejected(
    tmp_path: Path, section: dict[str, Any], message: str
) -> None:
    """Each way the section is wrong is an error."""
    with pytest.raises(ValueError, match=message):
        render_all(_write(tmp_path, clocks=section), tmp_path)


def test_the_core_phase_is_a_symbol_of_the_checks(tmp_path: Path) -> None:
    """The `clocks.core` entry names the phase of the core clock."""
    check = {
        "name": "core phase",
        "file": "pll.v",
        "pattern": r'phase_shift3\("(\d+) ps"',
        "expect": "CLOCKS.core_phase_ps",
    }
    path = _write(tmp_path, checks=[check])
    (tmp_path / "pll.v").write_text('.phase_shift3("7500 ps"),\n')
    check_equal(check_memory_map(path, tmp_path)[1], [])
    (tmp_path / "pll.v").write_text('.phase_shift3("6625 ps"),\n')
    check_equal(
        [m.check for m in check_memory_map(path, tmp_path)[1]], ["core phase"]
    )


def test_a_check_ties_the_pll_file_to_the_section(tmp_path: Path) -> None:
    """A PLL file in step passes and one out of step fails."""
    checks = [
        {
            "name": "frequency",
            "file": "pll.v",
            "pattern": r'output_clock_frequency0\("(\d+)\.',
            "expect": "CLOCKS.mem_mhz",
        },
    ]
    path = _write(tmp_path, checks=checks)
    (tmp_path / "pll.v").write_text(PLL)
    count, found = check_memory_map(path, tmp_path)
    check_equal(count, len(checks))
    check_equal(found, [])
    (tmp_path / "pll.v").write_text(PLL.replace("100", "133"))
    _, found = check_memory_map(path, tmp_path)
    check_equal([m.check for m in found], ["frequency"])


def test_the_tick_is_a_symbol_of_the_checks(tmp_path: Path) -> None:
    """The `interrupts` section names the cycles per `mtime` tick."""
    check = {
        "name": "tick",
        "file": "hdr.h",
        "pattern": r"RV32_TICK_CYCLES\s+(\d+)",
        "expect": "INTERRUPTS.tick_cycles",
    }
    path = _write(
        tmp_path,
        extras=["Interrupts"],
        interrupts={"mtime_hz": 1000000},
        peripherals=[{"name": "CLINT", "base": "0xE0000000", "size": "64K"}],
        checks=[check],
    )
    (tmp_path / "hdr.h").write_text("#define RV32_TICK_CYCLES 77\n")
    check_equal(check_memory_map(path, tmp_path)[1], [])
    (tmp_path / "hdr.h").write_text("#define RV32_TICK_CYCLES 50\n")
    check_equal(
        [m.check for m in check_memory_map(path, tmp_path)[1]], ["tick"]
    )
