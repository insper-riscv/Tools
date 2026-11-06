"""Tests for the clock of the SDRAM controller in the platform."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_in,
    check_not_in,
)

from riscv_tools.memory_map import render_all, set_override
from riscv_tools.memory_map.checks import check_memory_map

PLATFORM: dict[str, Any] = {
    "profile": "rv32i_zicsr",
    "profiles": "matrix.yaml",
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "sdram": {"clock_hz": 100000000, "dram_clk_phase_ps": 4000},
    "generate": {
        "runtime": {"path": "gen/rv32.h", "ram": "RAM"},
        "vhdl": {
            "path": "gen/clk_pkg.vhd",
            "package": "clk_pkg",
            "rom": "FLASH",
            "ram": "RAM",
            "ext_base": "0x80000000",
        },
    },
}

PLL = (
    '.output_clock_frequency0("100.000000 MHz"),\n.phase_shift1("4000 ps"),\n'
)


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


def test_the_package_has_the_clock_and_the_period(tmp_path: Path) -> None:
    """The VHDL package carries the rate and the period in ps."""
    text = render_all(_write(tmp_path), tmp_path)[tmp_path / "gen/clk_pkg.vhd"]
    check_in("constant SDRAM_CLOCK_HZ : positive := 100000000;", text)
    check_in("constant SDRAM_TCK_PS   : positive := 10000;", text)


def test_without_the_section_nothing_is_added(tmp_path: Path) -> None:
    """Without `sdram` there are no constants."""
    files = render_all(_write(tmp_path, sdram=None), tmp_path)
    check_not_in("SDRAM_TCK_PS", files[tmp_path / "gen/clk_pkg.vhd"])


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ({"clock_hz": 100000000}, "dram_clk_phase_ps is missing"),
        (
            {"clock_hz": 3000000000, "dram_clk_phase_ps": 0},
            "no whole period",
        ),
        (
            {"clock_hz": 100000000, "dram_clk_phase_ps": 10000},
            "not inside one period",
        ),
    ],
)
def test_an_inconsistent_section_is_rejected(
    tmp_path: Path, section: dict[str, Any], message: str
) -> None:
    """Each way the section is wrong is an error."""
    with pytest.raises(ValueError, match=message):
        render_all(_write(tmp_path, sdram=section), tmp_path)


def test_the_core_phase_is_a_symbol_of_the_checks(tmp_path: Path) -> None:
    """The `pll` section names the phase of the core clock."""
    check = {
        "name": "core phase",
        "file": "pll.v",
        "pattern": r'phase_shift3\("(\d+) ps"',
        "expect": "PLL.core_phase_ps",
    }
    path = _write(tmp_path, pll={"core_phase_ps": 8250}, checks=[check])
    (tmp_path / "pll.v").write_text('.phase_shift3("8250 ps"),\n')
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
            "expect": "SDRAM.clock_mhz",
        },
        {
            "name": "phase",
            "file": "pll.v",
            "pattern": r'phase_shift1\("(\d+) ps"',
            "expect": "SDRAM.dram_clk_phase_ps",
        },
    ]
    path = _write(tmp_path, checks=checks)
    (tmp_path / "pll.v").write_text(PLL)
    count, found = check_memory_map(path, tmp_path)
    check_equal(count, len(checks))
    check_equal(found, [])
    (tmp_path / "pll.v").write_text(PLL.replace("4000", "3000"))
    _, found = check_memory_map(path, tmp_path)
    check_equal([m.check for m in found], ["phase"])
