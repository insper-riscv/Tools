"""Tests for the peripherals given by base and size."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check,
    check_equal,
    check_in,
    check_not_in,
)

from riscv_tools.memory_map import (
    render_all,
    symbols,
    validate_platform,
)
from riscv_tools.memory_map.core import window_of

PLATFORM: dict[str, Any] = {
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "generate": {
        "vhdl": {
            "package": "offsets_pkg",
            "path": "out/offsets_pkg.vhd",
            "ram": "RAM",
            "rom": "FLASH",
        },
    },
}


def _with(*peripherals: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Copy the platform with the given peripherals."""
    return {**PLATFORM, "peripherals": list(peripherals), **changes}


def _problems(platform: dict[str, Any]) -> list[str]:
    """List the problems of the platform as text."""
    return [str(p) for p in validate_platform(platform)]


def _has(problems: list[str], text: str) -> None:
    """Check that one problem has the text."""
    check(any(text in p for p in problems), str(problems))


@pytest.mark.parametrize(
    ("size", "window"),
    [(1, 16), (4, 16), (16, 16), (17, 32), (64, 64), (1024, 1024), (65, 128)],
)
def test_the_window_is_the_next_power_of_two_with_16_bytes_at_least(
    size: int, window: int
) -> None:
    """The window is derived from `size`."""
    check_equal(window_of(size), window)


def test_the_symbols_have_the_base_the_size_the_window_and_the_index() -> None:
    """`base` and `size` give `window` and the order gives `index`."""
    platform = _with(
        {"name": "UART", "base": "0xC0000000", "size": "20"},
        {"name": "PLIC", "base": "0xF0000000", "size": "4M"},
    )
    table = symbols(platform)
    check_equal(table["UART.base"], 0xC0000000)
    check_equal(table["UART.size"], 20)
    check_equal(table["UART.window"], 32)
    check_equal(table["UART.index"], 0)
    check_equal(table["PLIC.window"], 4 * 1024 * 1024)
    check_equal(table["PLIC.index"], 1)
    check_equal(_problems(platform), [])


def test_a_base_in_the_low_half_is_a_peripheral_like_any_other() -> None:
    """The core has no peripheral window, so any free address works."""
    platform = _with({"name": "DISPLAY", "base": "0x80001000", "size": "4"})
    check_equal(_problems(platform), [])
    free = _with({"name": "LEDS", "base": "0x50000000", "size": "1K"})
    check_equal(_problems(free), [])


@pytest.mark.parametrize("field", ["id", "offset", "padding"])
def test_a_removed_field_is_refused_with_the_migration(field: str) -> None:
    """V-P1: `id`, `offset` and `padding` are no longer accepted."""
    platform = _with(
        {"name": "A", "base": "0xC0000000", "size": "16", field: "1"}
    )
    problems = _problems(platform)
    _has(problems, f"V-P1 peripheral A: `{field}` is no longer accepted")
    _has(problems, "`id: 5` becomes `base: 0xD0000000`")


def test_v_p1_base_and_size_are_needed() -> None:
    """V-P1: an entry without `base` or without `size` is refused."""
    _has(_problems(_with({"name": "A", "size": "16"})), "`base` is missing")
    _has(
        _problems(_with({"name": "A", "base": "0xC0000000"})),
        "`size` is missing",
    )
    _has(
        _problems(_with({"name": "A", "base": "0xC0000000", "size": "0"})),
        "`size` must be positive",
    )


def test_v_p2_the_base_must_be_aligned_to_the_window() -> None:
    """V-P2: a base that is not a multiple of the window is refused."""
    bad = _with({"name": "A", "base": "0xC0000020", "size": "64"})
    _has(_problems(bad), "V-P2 peripheral A base 0xC0000020")
    good = _with({"name": "A", "base": "0xC0000040", "size": "64"})
    check_equal(_problems(good), [])


def test_v_p4_peripherals_must_not_overlap() -> None:
    """V-P4: two windows take the same bytes."""
    clash = _with(
        {"name": "A", "base": "0xC0000000", "size": "1K"},
        {"name": "B", "base": "0xC0000200", "size": "16"},
    )
    _has(_problems(clash), "V-P4 peripherals A and B overlap")
    apart = _with(
        {"name": "A", "base": "0xC0000000", "size": "1K"},
        {"name": "B", "base": "0xC0000400", "size": "16"},
    )
    check_equal(_problems(apart), [])


def test_the_window_of_a_peripheral_counts_not_only_its_size() -> None:
    """The bytes after the registers belong to the window (V-P4)."""
    clash = _with(
        {"name": "A", "base": "0xC0000000", "size": "20"},
        {"name": "B", "base": "0xC0000010", "size": "16"},
    )
    _has(_problems(clash), "V-P4 peripherals A and B overlap")


def test_v_p5_a_peripheral_must_not_overlap_a_region() -> None:
    """V-P5: a window over the RAM, the FLASH or the BOOT_MEMORY."""
    over_ram = _with({"name": "A", "base": "0x10000", "size": "16"})
    _has(_problems(over_ram), "V-P5 peripheral A and RAM overlap")
    over_boot = _with({"name": "B", "base": "0x0", "size": "16"})
    _has(_problems(over_boot), "V-P5 peripheral B and BOOT_MEMORY overlap")


def test_v_a4_the_window_must_fit_the_address_space() -> None:
    """V-A4: a window that goes past `2**address_bits`."""
    bad = _with({"name": "A", "base": "0xFFFFFFF0", "size": "64"})
    _has(_problems(bad), "V-A4 peripheral A window")


def test_the_tables_follow_the_order_of_the_platform(tmp_path: Path) -> None:
    """The tables list the peripherals in the order of the platform."""
    platform = _with(
        {"name": "UART", "base": "0xC0000000", "size": "16"},
        {"name": "PLIC", "base": "0xF0000000", "size": "4M"},
    )
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    text = render_all(path, tmp_path)[tmp_path / "out/offsets_pkg.vhd"]
    for line in (
        "constant PERIPH_COUNT : natural := 2;",
        "constant UART_INDEX : natural := 0;",
        "constant PLIC_INDEX : natural := 1;",
        "type periph_addr_array_t is array (natural range <>) of addr_t;",
        "UART_INDEX => UART_BASE,\n\t\tPLIC_INDEX => PLIC_BASE",
        'std_logic_vector(resize(unsigned\'(x"FFFFFFF0"), ADDR_BITS)),',
        'std_logic_vector(resize(unsigned\'(x"FFC00000"), ADDR_BITS))\n',
    ):
        check_in(line, text)
    for gone in ("_ID ", "_OFFSET", "_PAD", "PERIPH_SLOTS", "EXT_BASE"):
        check_not_in(gone, text)


def test_a_platform_without_peripherals_has_empty_tables(
    tmp_path: Path,
) -> None:
    """Zero peripherals write null tables, which elaborate."""
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(_with(), sort_keys=False))
    text = render_all(path, tmp_path)[tmp_path / "out/offsets_pkg.vhd"]
    check_in("constant PERIPH_COUNT : natural := 0;", text)
    check_in("others => (others => '0')", text)


def test_strict_periph_must_be_a_boolean() -> None:
    """V-S1: a `strict_periph` that is not true or false is refused."""
    _has(_problems(_with(strict_periph="yes")), "V-S1 strict_periph")
    check_equal(_problems(_with(strict_periph=False)), [])
    check_equal(_problems(_with()), [])


@pytest.mark.parametrize("strict", [True, False])
def test_strict_periph_is_a_constant_of_the_map_package(
    tmp_path: Path, strict: bool
) -> None:
    """The policy of the interconnect is written in the map package."""
    platform = _with(
        {"name": "PLIC", "base": "0xF0000000", "size": "4M"},
        strict_periph=strict,
    )
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    out = render_all(path, tmp_path)[tmp_path / "out/offsets_pkg.vhd"]
    check_in(
        f"constant STRICT_PERIPH : boolean := {str(strict).lower()};", out
    )
