"""Tests for the general-purpose timers of the platform (any number)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_in,
    check_not_in,
    write_zicsr_platform,
)

from riscv_tools.memory_map import load_platform, render_all
from riscv_tools.memory_map.config_pkg import render_variant
from riscv_tools.memory_map.interrupts import sources_of
from riscv_tools.top_generator.generics import timer_generics
from riscv_tools.top_generator.spec import TopSpec

CLINT = {"name": "CLINT", "base": "0xE0000000", "size": "64K"}
PLIC = {"name": "PLIC", "base": "0xF0000000", "size": "4M"}
UART = {"name": "UART", "base": "0xC0000000", "size": "1K"}


def _timer(name: str, base: int, **extra: Any) -> dict[str, Any]:
    """Write one timer entry, 64 bytes wide."""
    return {
        "name": name,
        "kind": "timer",
        "base": f"{base:#x}",
        "size": 64,
        **extra,
    }


def _platform(
    peripherals: list[dict[str, Any]], sources: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Return a platform with interrupts, the PLIC and the timers."""
    interrupts: dict[str, Any] = {"clock_hz": 50000000, "mtime_hz": 1000000}
    if sources is not None:
        interrupts |= {"plic": {"priority_bits": 3}, "sources": sources}
    return {
        "profile": "rv32i_zicsr",
        "profiles": "matrix.yaml",
        "extras": ["Interrupts"],
        "regions": MAP_REGIONS,
        "reserved": MAP_RESERVED,
        "boot": {"entry": "0x800", "wait_restart": "0x100"},
        "peripherals": peripherals,
        "interrupts": interrupts,
        "generate": {
            "runtime": {"path": "gen/rv32.h", "ram": "RAM"},
            "vhdl": {
                "path": "gen/map_pkg.vhd",
                "package": "map_pkg",
                "rom": "FLASH",
                "ram": "RAM",
            },
        },
    }


def _three(tmp_path: Path) -> Path:
    """Write the platform with UART, the PLIC and three timers."""
    peripherals = [
        UART,
        _timer("TIMER0", 0x80006000),
        _timer("TIMER1", 0x80006100),
        _timer("TIMER2", 0x80006200),
        CLINT,
        PLIC,
    ]
    sources = [{"name": "UART", "id": 1}, {"name": "FLASH", "id": 6}]
    return write_zicsr_platform(tmp_path, _platform(peripherals, sources))


def test_three_timers_get_a_window_and_a_line_each(tmp_path: Path) -> None:
    """The tables list the timers in the order of `peripherals`."""
    text = render_all(_three(tmp_path), tmp_path)[tmp_path / "gen/map_pkg.vhd"]
    check_in("constant TIMER0_BASE : addr_t", text)
    check_in("constant TIMER2_INDEX : natural := 3;", text)
    check_in("constant TIMER_COUNT : natural := 3;", text)
    check_in("0 => TIMER0_INDEX,\n\t\t1 => TIMER1_INDEX,", text)
    check_in(
        "0 => IRQ_TIMER0,\n\t\t1 => IRQ_TIMER1,\n\t\t2 => IRQ_TIMER2", text
    )
    check_in("constant IRQ_TIMER0 : positive := 5;", text)
    check_in("constant IRQ_TIMER1 : positive := 7;", text)
    check_in("constant IRQ_TIMER2 : positive := 8;", text)
    check_in("constant PLIC_N_SOURCES     : positive := 8;", text)


def test_the_header_names_each_timer(tmp_path: Path) -> None:
    """The runtime header has the base and the line of every timer."""
    header = render_all(_three(tmp_path), tmp_path)[tmp_path / "gen/rv32.h"]
    check_in("#define RV32_TIMER1_BASE RV32_ADDRESS(0x80006100)", header)
    check_in("#define RV32_IRQ_TIMER0 RV32_ADDRESS(0x00000005)", header)
    check_in("#define RV32_IRQ_TIMER2 RV32_ADDRESS(0x00000008)", header)


def test_has_timer_follows_the_timers(tmp_path: Path) -> None:
    """HAS_TIMER is true with one timer or more and false with none."""
    path = _three(tmp_path)
    text = render_variant(load_platform(path), path, tmp_path)
    check_in("constant HAS_TIMER      : boolean := true;", text)
    bare = write_zicsr_platform(
        tmp_path, _platform([UART, CLINT, PLIC], [{"name": "UART", "id": 1}])
    )
    text = render_variant(load_platform(bare), bare, tmp_path)
    check_in("constant HAS_TIMER      : boolean := false;", text)


def test_no_timer_gives_empty_tables(tmp_path: Path) -> None:
    """Without timers the count is zero and the tables are empty."""
    platform = _platform([UART, CLINT, PLIC], [{"name": "UART", "id": 1}])
    path = write_zicsr_platform(tmp_path, platform)
    text = render_all(path, tmp_path)[tmp_path / "gen/map_pkg.vhd"]
    check_in("constant TIMER_COUNT : natural := 0;", text)
    check_in("TIMER_INDICES : integer_vector(0 to TIMER_COUNT - 1)", text)
    check_not_in("TIMER0", text)


def test_the_name_timer_is_still_a_timer(tmp_path: Path) -> None:
    """The entry TIMER with no kind keeps its pinned line."""
    timer = {"name": "TIMER", "base": "0x80000000", "size": 32}
    sources = [{"name": "UART", "id": 1}, {"name": "TIMER", "id": 5}]
    path = write_zicsr_platform(
        tmp_path, _platform([timer, UART, CLINT, PLIC], sources)
    )
    text = render_all(path, tmp_path)[tmp_path / "gen/map_pkg.vhd"]
    check_in("constant TIMER_COUNT : natural := 1;", text)
    check_in("0 => TIMER_INDEX", text)
    check_in("0 => IRQ_TIMER\n", text)
    check_in("constant IRQ_TIMER : positive := 5;", text)


def test_a_timer_without_a_source_takes_the_old_line(tmp_path: Path) -> None:
    """One unpinned TIMER lands on 5, where the SoC always put it."""
    timer = {"name": "TIMER", "base": "0x80000000", "size": 32}
    path = write_zicsr_platform(
        tmp_path,
        _platform([timer, UART, CLINT, PLIC], [{"name": "UART", "id": 1}]),
    )
    check_equal(sources_of(load_platform(path)), [("UART", 1), ("TIMER", 5)])


@pytest.mark.parametrize("count", [0, 1, 3, 8])
def test_the_other_sources_never_move(tmp_path: Path, count: int) -> None:
    """The listed sources keep their numbers whatever the timers."""
    timers = [_timer(f"T{i}", 0x80006000 + 0x100 * i) for i in range(count)]
    listed = [
        {"name": "UART", "id": 1},
        {"name": "KEYS", "id": 4},
        {"name": "FLASH", "id": 6},
    ]
    path = write_zicsr_platform(
        tmp_path, _platform([*timers, CLINT, PLIC], listed)
    )
    found = sources_of(load_platform(path))
    check_equal(found[:3], [(s["name"], s["id"]) for s in listed])
    lines = [ident for _, ident in found[3:]]
    check_equal(lines, [5, 7, 8, 9, 10, 11, 12, 13][:count])


def test_timers_without_a_plic_have_no_line(tmp_path: Path) -> None:
    """With no PLIC the table of lines is zero."""
    platform = _platform([_timer("T0", 0x80006000), CLINT], None)
    path = write_zicsr_platform(tmp_path, platform)
    text = render_all(path, tmp_path)[tmp_path / "gen/map_pkg.vhd"]
    check_in("constant TIMER_COUNT : natural := 1;", text)
    check_in(
        "TIMER_IRQ_IDS : integer_vector(0 to TIMER_COUNT - 1) := (\n"
        "\t\t0 => 0",
        text,
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"kind": "counter"}, "V-P6 peripheral T0: kind 'counter'"),
        ({"size": 16}, "V-P7 peripheral T0: a timer needs"),
        ({"name": "T-0"}, "V-P8 peripheral T-0"),
        ({"base": "0x80006020"}, "V-P2 peripheral T0"),
    ],
)
def test_a_wrong_timer_is_refused(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    """Kind, window size, name and alignment are checked."""
    timer = _timer("T0", 0x80006000) | change
    path = write_zicsr_platform(
        tmp_path, _platform([timer, CLINT, PLIC], [{"name": "UART", "id": 1}])
    )
    with pytest.raises(ValueError, match=message):
        render_all(path, tmp_path)


def test_two_timers_may_not_overlap(tmp_path: Path) -> None:
    """The windows of two timers are checked like any other pair."""
    timers = [_timer("T0", 0x80006000), _timer("T1", 0x80006000)]
    path = write_zicsr_platform(
        tmp_path,
        _platform([*timers, CLINT, PLIC], [{"name": "UART", "id": 1}]),
    )
    with pytest.raises(ValueError, match="V-P4"):
        render_all(path, tmp_path)


def test_a_timer_cannot_take_a_fixed_line(tmp_path: Path) -> None:
    """A source id that the SoC gives to the UART is refused."""
    sources = [{"name": "T0", "id": 1}]
    path = write_zicsr_platform(
        tmp_path,
        _platform([_timer("T0", 0x80006000), CLINT, PLIC], sources),
    )
    with pytest.raises(ValueError, match="V-P9 peripheral T0"):
        render_all(path, tmp_path)


def _spec(platform: dict[str, Any]) -> TopSpec:
    """Stand in for the top, whose timer generics read the platform."""
    return cast(TopSpec, SimpleNamespace(platform=platform))


def test_the_board_top_passes_the_timer_tables(tmp_path: Path) -> None:
    """The generated top gives the SoC one timer per table row."""
    platform = load_platform(_three(tmp_path))
    check_equal(
        timer_generics(_spec(platform)),
        ["timer_indices => TIMER_INDICES", "timer_irq_ids => TIMER_IRQ_IDS"],
    )


def test_the_board_top_without_timers_is_unchanged() -> None:
    """A platform with no timer adds no generic to the top."""
    check_equal(timer_generics(_spec({"peripherals": []})), [])
