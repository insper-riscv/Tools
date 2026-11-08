"""Tests for the peripherals given by offset, id and padding."""

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


def test_an_offset_gives_the_same_map_as_the_absolute_base() -> None:
    """`offset` and `base` write the same symbols, `id` is derived."""
    absolute = _with({"name": "UART", "base": "0xC0000000", "id": 4})
    relative = _with({"name": "UART", "offset": "0x40000000"})
    check_equal(symbols(absolute)["UART.base"], 0xC0000000)
    check_equal(symbols(relative)["UART.base"], 0xC0000000)
    check_equal(symbols(relative)["UART.id"], 4)
    check_equal(symbols(absolute)["UART.offset"], 0x40000000)
    check_equal(_problems(relative), [])


def test_an_absolute_base_without_id_is_converted_to_an_offset() -> None:
    """The `id` is optional with `base` too."""
    platform = _with({"name": "UART", "base": "0xC0000000"})
    check_equal(symbols(platform)["UART.id"], 4)
    check_equal(_problems(platform), [])


def test_the_same_offsets_hold_for_another_address_width() -> None:
    """The window follows `address_bits`, the offset stays."""
    platform = _with(
        {"name": "UART", "offset": "0x500000"},
        address_bits=24,
    )
    table = symbols(platform)
    check_equal(table["UART.base"], 0x800000 + 0x500000)
    check_equal(table["UART.id"], 5)
    check_equal(_problems(platform), [])


def test_v_p1_exactly_one_of_base_and_offset() -> None:
    """V-P1: neither, both, or a base below the window is refused."""
    _has(_problems(_with({"name": "A", "id": 1})), "V-P1 peripheral A")
    both = _with({"name": "A", "base": "0xC0000000", "offset": "0x40000000"})
    _has(_problems(both), "V-P1 peripheral A: exactly one of")
    below = _with({"name": "A", "base": "0x70000000"})
    _has(_problems(below), "V-P1 peripheral A base 0x70000000 is below")


def test_v_p2_a_given_id_must_match_the_offset() -> None:
    """V-P2: the `id` is the slot of the offset."""
    wrong = _with({"name": "A", "offset": "0x40000000", "id": 3})
    _has(_problems(wrong), "V-P2 peripheral A base is not in the slot of id 3")


def test_v_p3_size_and_padding_must_fit_the_slot() -> None:
    """V-P3: size plus padding goes past the end of the slot."""
    big = _with(
        {"name": "A", "offset": "0x40000000", "size": "4M", "padding": "256M"}
    )
    _has(_problems(big), "V-P3 peripheral A: size + padding")
    fits = _with(
        {"name": "A", "offset": "0x40000000", "size": "4M", "padding": "4M"}
    )
    check_equal(_problems(fits), [])


def test_v_p4_peripherals_must_not_overlap() -> None:
    """V-P4: two peripherals take the same bytes of a slot."""
    clash = _with(
        {"name": "A", "offset": "0x40000000", "size": "1M", "padding": "1M"},
        {"name": "B", "offset": "0x40100000", "size": "1M"},
    )
    _has(_problems(clash), "V-P4 peripherals A and B overlap")
    apart = _with(
        {"name": "A", "offset": "0x40000000", "size": "1M", "padding": "1M"},
        {"name": "B", "offset": "0x40200000", "size": "1M", "padding": "1M"},
    )
    check_equal(_problems(apart), [])
    whole_slot = _with(
        {"name": "A", "offset": "0x40000000", "size": "1M"},
        {"name": "B", "offset": "0x40100000", "size": "1M"},
    )
    _has(_problems(whole_slot), "V-P4")


def test_the_map_package_writes_offset_size_and_padding(
    tmp_path: Path,
) -> None:
    """A relative peripheral gets three more constants."""
    platform = _with(
        {"name": "UART", "base": "0xC0000000", "id": 4},
        {
            "name": "PLIC",
            "offset": "0x70000000",
            "size": "4M",
            "padding": "4M",
        },
    )
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    text = render_all(path, tmp_path)[tmp_path / "out/offsets_pkg.vhd"]
    check_in(
        'constant PLIC_BASE : std_logic_vector(31 downto 0) := x"F0000000";',
        text,
    )
    check_in(
        'constant PLIC_OFFSET : std_logic_vector(31 downto 0) := x"70000000";',
        text,
    )
    check_in("constant PLIC_SIZE   :", text)
    check_in('x"00400000"', text)
    check_not_in("UART_OFFSET", text)
    check_not_in("UART_PAD", text)


@pytest.mark.parametrize("field", ["offset", "padding"])
def test_a_legacy_entry_has_no_relative_constants(
    tmp_path: Path, field: str
) -> None:
    """The entries of today, with `base` and `id`, write nothing new."""
    platform = _with({"name": "UART", "base": "0xC0000000", "id": 4})
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    text = render_all(path, tmp_path)[tmp_path / "out/offsets_pkg.vhd"]
    check_not_in(f"UART_{field.upper()}", text)
