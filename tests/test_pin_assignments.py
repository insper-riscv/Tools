"""Tests for pin_assignments."""

from dataclasses import replace

import pytest
from multifpga_support import inputs_of
from support import check_equal, check_in, check_not_in

from riscv_tools.board_ports import build_ports
from riscv_tools.pin_assignments import PinError, render_pins


def _text() -> str:
    """Pins of the DE0-CV fixture."""
    return render_pins(build_ports(inputs_of("de0-cv")).ports, True)


def test_locations_and_standards_come_from_the_pins_file() -> None:
    """One location and one standard per bit."""
    text = _text()
    check_in("set_location_assignment PIN_M9 -to CLOCK_50", text)
    check_in("set_location_assignment PIN_P22 -to FPGA_RESET_N", text)
    check_in("set_location_assignment PIN_AA2 -to LEDR[0]", text)
    check_in(
        'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to HEX5[6]',
        text,
    )
    check_equal(
        text.count("set_location_assignment"),
        1 + 1 + 10 + 10 + 4 + 42 + 13 + 16 + 2 + 8,
    )


def test_the_sdram_role_derives_the_io_registers() -> None:
    """FAST_* registers come from the role, never from a copied file."""
    text = _text()
    check_in("FAST_OUTPUT_REGISTER ON -to DRAM_ADDR[*]", text)
    check_in("FAST_OUTPUT_REGISTER ON -to DRAM_DQ[*]", text)
    check_in("FAST_OUTPUT_ENABLE_REGISTER ON -to DRAM_DQ[*]", text)
    check_in("FAST_INPUT_REGISTER ON -to DRAM_DQ[*]", text)
    check_in("PAD_TO_INPUT_REGISTER_DELAY 0 -to DRAM_DQ[*]", text)
    check_not_in("FAST_OUTPUT_REGISTER ON -to DRAM_CLK", text)


def test_slow_outputs_get_the_slew_and_current_assignments() -> None:
    """LEDs and displays take the default current and the slow slew."""
    text = _text()
    check_in("CURRENT_STRENGTH_NEW DEFAULT -to LEDR\n", text)
    check_in("SLEW_RATE 1 -to HEX3\n", text)
    check_not_in("SLEW_RATE 1 -to DRAM", text)


def test_an_inferred_pin_is_refused_without_the_option() -> None:
    """V16: the message names the pin and the signal."""
    inputs = inputs_of("de2-115")
    signals = dict(inputs.signals)
    signals["CLOCK_50"] = replace(signals["CLOCK_50"], confirmed="inferred")
    ports = build_ports(replace(inputs, signals=signals)).ports
    with pytest.raises(PinError, match=r"pin Y2 for CLOCK_50 is inferred"):
        render_pins(ports)
    check_in("PIN_Y2", render_pins(ports, accept_inferred=True))


def test_a_pin_is_never_assigned_twice() -> None:
    """Two bits on one pin are refused (aliases in pins.yaml)."""
    inputs = inputs_of("de0-cv")
    signals = dict(inputs.signals)
    signals["LEDR[1]"] = replace(
        signals["LEDR[1]"], pin=signals["LEDR[0]"].pin
    )
    ports = build_ports(replace(inputs, signals=signals)).ports
    with pytest.raises(
        PinError, match="assigned to both LEDR\\[0\\] and LEDR\\[1\\]"
    ):
        render_pins(ports, True)


def test_unused_conflicting_aliases_are_not_assigned() -> None:
    """The SPI_FLASH aliases of GPIO_0 are not in the used ports."""
    check_not_in("SPI_FLASH", _text())
    check_not_in("GPIO_0", _text())
