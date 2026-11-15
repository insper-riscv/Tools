"""Tests of the fields of the external kinds and their generics."""

import re
from fractions import Fraction
from typing import Any

import pytest
from support import check, check_equal, check_in

from riscv_tools.board_clocks import ClockPlan
from riscv_tools.memory_map import kinds
from riscv_tools.memory_map.external_entry import entry
from riscv_tools.top_generator.external import instance_generics
from riscv_tools.top_generator.spec import TopSpec

HDMI: dict[str, Any] = {
    "kind": "hdmi",
    "base": 0x80200000,
    "fb_width": 640,
    "fb_height": 360,
    "pixel_format": "direct",
    "scale": 2,
    "h_visible": 1280,
    "h_front_porch": 110,
    "h_sync": 40,
    "h_back_porch": 220,
    "h_sync_positive": True,
    "v_visible": 720,
    "v_front_porch": 5,
    "v_sync": 5,
    "v_back_porch": 20,
    "v_sync_positive": False,
    "mode_id": 4,
    "pixel_clock_khz": 74250,
    "init_enable": True,
    "init_auto_start": False,
    "init_table": "98030198",
    "audio_init_table": "0a00",
    "i2c_dev_addr": 57,
    "i2c_freq": 400000,
    "int_active_low": False,
}


def _spec() -> TopSpec:
    """Make a top with the 50 MHz fallback clock and no pins."""
    plan = ClockPlan("CLOCK_50", Fraction(50), ())
    return TopSpec({}, plan, (), "pll", "top", {})


def _generics(item: dict[str, Any]) -> list[str]:
    """Give the generic map the top writes for one entry."""
    done = entry("X", item)
    kind = kinds.EXTERNAL[str(item["kind"])]
    variant = kind.variant(done)
    if variant is None:
        pytest.fail("the kind has no entity")
    return instance_generics(_spec(), done, variant, kind)


def test_hdmi_fields_become_the_generics_of_the_transmitter() -> None:
    """Each field of the `hdmi` kind is the generic of `hdmi_tx`."""
    found = _generics(HDMI)
    for text in (
        "clk_freq => 50000000",
        "fb_width => 640",
        "fb_height => 360",
        'pixel_format => "direct"',
        "scale => 2",
        "h_visible => 1280",
        "h_sync_positive => true",
        "v_sync_positive => false",
        "mode_id => 4",
        "pixel_clock_khz => 74250",
        "init_enable => true",
        "init_auto_start => false",
        'init_table => "98030198"',
        'audio_init_table => "0a00"',
        'i2c_dev_addr => "0111001"',
        "i2c_freq => 400000",
        "int_active_low => false",
    ):
        check_in(text, found)
    check_equal(len(found), len(HDMI) - 1)


def test_only_the_fields_written_become_generics() -> None:
    """An entry without fields leaves every default to the entity."""
    check_equal(
        _generics({"kind": "hdmi", "base": 0}), ["clk_freq => 50000000"]
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"pixel_format": "rgb"}, "must be one of ['indexed', 'direct']"),
        ({"init_table": "98zz"}, "must be hexadecimal"),
        ({"init_table": "980"}, "must be hexadecimal"),
        ({"i2c_dev_addr": 128}, "from 0 to 127"),
        ({"scale": 0}, "must be at least 1"),
        ({"fb_width": "320"}, "must be of type int"),
        ({"init_enable": 1}, "must be of type bool"),
        ({"h_front_porch": -1}, "must be at least 0"),
    ],
)
def test_a_hdmi_field_with_a_bad_value_is_refused(
    changes: dict[str, Any], message: str
) -> None:
    """The type, the choices and the limits are checked on reading."""
    with pytest.raises(ValueError, match=re.escape(message)):
        entry("X", {"kind": "hdmi", "base": 0, **changes})


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (
            {"kind": "ps2", "device": "mouse", "rx_fifo_depth": 8},
            "does not apply to device mouse",
        ),
        (
            {"kind": "ps2", "device": "keyboard", "packet_timeout_cycles": 9},
            "does not apply to device keyboard",
        ),
        (
            {"kind": "adc", "chip": "ltc2308", "scan_freq": 10},
            "does not apply to chip ltc2308",
        ),
        (
            {"kind": "adc", "chip": "max10", "sclk_hz": 10},
            "does not apply to chip max10",
        ),
        (
            {"kind": "adc", "chip": "ltc2308", "channel_latency": 2},
            "must be at most 1",
        ),
        ({"kind": "usb", "setup_cycles": 256}, "must be at most 255"),
        ({"kind": "spi", "word_width": 33}, "must be at most 32"),
    ],
)
def test_a_field_of_another_entity_or_out_of_range_is_refused(
    item: dict[str, Any], message: str
) -> None:
    """A generic that the chosen entity lacks never reaches its map."""
    with pytest.raises(ValueError, match=re.escape(message)):
        entry("X", {"base": 0, **item})


def test_the_fields_of_the_entity_chosen_are_generics() -> None:
    """The mouse and the ltc2308 take their own generics."""
    mouse = _generics(
        {
            "kind": "ps2",
            "device": "mouse",
            "base": 0,
            "filter_cycles": 4,
            "init_timeout_cycles": 1000,
        }
    )
    check_equal(mouse, ["filter_cycles => 4", "init_timeout_cycles => 1000"])
    adc = _generics(
        {
            "kind": "adc",
            "chip": "ltc2308",
            "base": 0,
            "sclk_hz": 5000000,
            "convst_ns": 120,
            "channel_latency": 0,
        }
    )
    check_equal(
        adc,
        [
            "clock_hz => 50000000",
            "sclk_hz => 5000000",
            "channel_latency => 0",
            "convst_ns => 120",
        ],
    )


def test_every_field_names_a_known_type_and_a_valid_entity() -> None:
    """The registry only uses the types and entities it defines."""
    for kind in kinds.EXTERNAL.values():
        names = [f.name for f in kind.fields]
        check_equal(len(names), len(set(names)), kind.name)
        for spec in kind.fields:
            check(spec.type in ("int", "bool", "choice", "hex", "addr7"))
            check(set(spec.only) <= set(kind.variants), spec.name)
            check(spec.generic != "", spec.name)
