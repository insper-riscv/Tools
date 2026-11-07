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


def test_the_tick_follows_the_core_clock(tmp_path: Path) -> None:
    """With `clocks.core` the clock rate is that clock rounded."""
    clocks = {"core": {"mhz": 76.923077, "phase_ps": 7500}}
    section = {"mtime_hz": 1000000}
    path = _write(tmp_path, clocks=clocks, interrupts=section)
    text = render_all(path, tmp_path)[tmp_path / "gen/irq_pkg.vhd"]
    check_in("constant CLOCK_HZ          : positive := 77000000;", text)
    check_in("constant CLINT_TICK_CYCLES : positive := 77;", text)
    stale = {"clock_hz": 50000000, "mtime_hz": 1000000}
    path = _write(tmp_path, clocks=clocks, interrupts=stale)
    with pytest.raises(ValueError, match="leave clock_hz out"):
        render_all(path, tmp_path)


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


PLIC_PLATFORM: dict[str, Any] = {
    "peripherals": [
        {"name": "CLINT", "base": "0xE0000000", "id": 6},
        {"name": "PLIC", "base": "0xF0000000", "id": 7, "size": "4M"},
    ],
    "interrupts": {
        "clock_hz": 50000000,
        "mtime_hz": 1000000,
        "plic": {"priority_bits": 3},
        "sources": [
            {"name": "UART", "id": 1},
            {"name": "TIMER", "id": 5},
        ],
    },
}


def test_the_package_has_the_plic_and_its_sources(tmp_path: Path) -> None:
    """The VHDL package carries the window width and the source ids."""
    text = render_all(_write(tmp_path, **PLIC_PLATFORM), tmp_path)[
        tmp_path / "gen/irq_pkg.vhd"
    ]
    check_in("constant PLIC_N_SOURCES     : positive := 5;", text)
    check_in("constant PLIC_PRIORITY_BITS : positive := 3;", text)
    check_in("constant PLIC_ADDR_WIDTH    : positive := 20;", text)
    check_in("constant IRQ_UART : positive := 1;", text)
    check_in("constant IRQ_TIMER : positive := 5;", text)


@pytest.mark.parametrize(
    ("macro", "value"),
    [
        ("RV32_PLIC_BASE", "0xF0000000"),
        ("RV32_PLIC_PRIORITY", "0xF0000000"),
        ("RV32_PLIC_PENDING", "0xF0001000"),
        ("RV32_PLIC_ENABLE", "0xF0002000"),
        ("RV32_PLIC_THRESHOLD", "0xF0200000"),
        ("RV32_PLIC_CLAIM", "0xF0200004"),
        ("RV32_IRQ_UART", "0x00000001"),
        ("RV32_IRQ_TIMER", "0x00000005"),
    ],
)
def test_the_header_has_the_registers_of_the_plic(
    tmp_path: Path, macro: str, value: str
) -> None:
    """The runtime header has the PLIC registers and the source ids."""
    files = render_all(_write(tmp_path, **PLIC_PLATFORM), tmp_path)
    check_in(
        f"#define {macro} RV32_ADDRESS({value})",
        files[tmp_path / "gen/rv32.h"],
    )


def _plic_with(**changes: Any) -> dict[str, Any]:
    """Return the PLIC platform with some sections changed."""
    base = yaml.safe_load(yaml.safe_dump(PLIC_PLATFORM))
    if "interrupts" in changes:
        base["interrupts"] |= changes["interrupts"]
    if "peripherals" in changes:
        base["peripherals"] = changes["peripherals"]
    return base


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "interrupts": {
                    "sources": [{"name": "A", "id": 1}, {"name": "B", "id": 1}]
                }
            },
            "repeat",
        ),
        ({"interrupts": {"sources": [{"name": "A", "id": 0}]}}, "outside"),
        ({"interrupts": {"plic": {"priority_bits": 40}}}, "priority_bits"),
        (
            {
                "peripherals": [
                    {"name": "CLINT", "base": "0xE0000000", "id": 6},
                    {
                        "name": "PLIC",
                        "base": "0xF0000000",
                        "id": 7,
                        "size": "64K",
                    },
                ]
            },
            "power of two",
        ),
        (
            {
                "peripherals": [
                    {"name": "CLINT", "base": "0xE0000000", "id": 6},
                    {"name": "PLIC", "base": "0xF0000000", "id": 7},
                ]
            },
            "has no size",
        ),
        (
            {
                "peripherals": [
                    {"name": "CLINT", "base": "0xE0000000", "id": 6}
                ]
            },
            "no PLIC",
        ),
    ],
)
def test_an_inconsistent_plic_is_rejected(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    """Each way the PLIC description is wrong is an error."""
    with pytest.raises(ValueError, match=message):
        render_all(_write(tmp_path, **_plic_with(**changes)), tmp_path)
