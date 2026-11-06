"""Tests for board_ports and board_clocks."""

import re
from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest
from multifpga_support import BOARD_NAMES, inputs_of, with_platform
from support import check, check_equal, check_false

from riscv_tools.board_clocks import ClockPlan, ClockRole, clock_plan
from riscv_tools.board_inputs import InputError
from riscv_tools.board_ports import build_ports, memory_clock_port


def test_the_de0_cv_ports_match_the_handwritten_top() -> None:
    """Widths, directions and names are those of de0-cv_top.vhd."""
    ports = {p.name: p for p in build_ports(inputs_of("de0-cv")).ports}
    check_equal(ports["LEDR"].width, 10)
    check_equal(ports["KEY"].width, 4)
    check_equal(ports["SW"].width, 10)
    for digit in range(6):
        check_equal(ports[f"HEX{digit}"].width, 7)
    check_equal(ports["DRAM_ADDR"].width, 13)
    check_equal(ports["DRAM_BA"].width, 2)
    check_equal(ports["DRAM_DQ"].width, 16)
    check_equal(ports["DRAM_DQ"].direction, "inout")
    check_false(ports["DRAM_CLK"].vector)
    check_equal(ports["FPGA_RESET_N"].active, "low")
    clock = memory_clock_port(tuple(ports.values()), "sdram")
    check(clock is not None and clock.name == "DRAM_CLK")


def test_flat_pin_names_become_vectors() -> None:
    """Pins named LEDR0, HEX00, DRAM_DQ0 still give vector ports."""
    inputs = inputs_of("de10-lite")
    flat = {}
    for name, sig in inputs.signals.items():
        flat[
            re.sub(r"\[(\d+)\]", r"\1", name)
            if "DRAM" in name or "LEDR" in name
            else name
        ] = sig
    flat_inputs = replace(inputs, signals=flat)
    ports = {p.name: p for p in build_ports(flat_inputs).ports}
    check_equal(ports["LEDR"].width, 10)
    check_equal(ports["DRAM_DQ"].width, 16)
    check_equal(ports["DRAM_BA"].width, 2)
    check_false(ports["DRAM_LDQM"].vector)


def test_the_reset_on_a_key_bit_is_an_alias() -> None:
    """A reset on KEY[0] reuses the KEY port and owns no pin."""
    keys = {"keys": {"count": 4, "need": "optional"}}
    inputs = with_platform(inputs_of("de2-115"), io=keys)
    ports = {p.name: p for p in build_ports(inputs).ports}
    check_equal(ports["KEY[0]"].alias, "KEY(0)")
    check_equal(ports["KEY"].width, 4)
    check_equal(ports["DRAM_DQM"].width, 4)
    check_equal(ports["DRAM_DQ"].width, 32)
    check_equal(ports["FL_DQ"].width, 8)


def test_the_sram_backend_gives_its_pins() -> None:
    """A RAM in the SRAM of the DE2-115 brings SRAM_DQ of 16 bits."""
    memory = {
        "rom": {"external": True, "backend": "emulado"},
        "ram": {"external": True, "backend": "dispositivo", "device": "sram"},
    }
    inputs = with_platform(inputs_of("de2-115"), memory=memory)
    ports = {p.name: p for p in build_ports(inputs).ports}
    check_equal(ports["SRAM_DQ"].width, 16)
    check_equal(ports["SRAM_ADDR"].width, 20)


def test_a_reset_bit_without_its_port_gets_a_port() -> None:
    """Without the KEY role the reset is a scalar port of its own."""
    ports = {p.name: p for p in build_ports(inputs_of("de2-115")).ports}
    check_equal(ports["KEY_0"].alias, "")
    check_equal(ports["KEY_0"].signals[0].name, "KEY[0]")


def test_a_two_prefix_memory_collects_both_groups() -> None:
    """The MKR names its SDRAM with the prefixes oSDRAM and bSDRAM."""
    memory = {
        "rom": {"external": True, "backend": "emulado"},
        "ram": {"external": True, "backend": "dispositivo", "device": "sdram"},
    }
    inputs = with_platform(inputs_of("mkr-vidor-4000"), memory=memory)
    ports = {p.name: p for p in build_ports(inputs).ports}
    check_equal(ports["bSDRAM_DQ"].width, 16)
    check_equal(ports["oSDRAM_ADDR"].width, 12)
    check_equal(ports["oSDRAM_CLK"].direction, "out")


def test_every_board_builds_ports_without_duplicate_names() -> None:
    """No board repeats a port name."""
    for name in BOARD_NAMES:
        names = [p.name for p in build_ports(inputs_of(name)).ports]
        check_equal(len(names), len(set(names)), name)


def test_a_missing_required_role_is_an_error() -> None:
    """V5: the MKR has no LEDs."""
    broken = with_platform(
        inputs_of("mkr-vidor-4000"),
        io={"leds": {"count": 10, "need": "required"}},
    )
    with pytest.raises(InputError, match=r"io\.leds count 10 required"):
        build_ports(broken)


def test_a_missing_optional_role_is_a_warning() -> None:
    """V6: the DE0-Nano has no display."""
    plan = build_ports(inputs_of("de0-nano"))
    check(any("io.display optional" in w for w in plan.warnings))


def test_the_pins_console_needs_a_uart() -> None:
    """V4: console pinos on a board without a UART is refused."""
    broken = with_platform(inputs_of("de10-lite"), console="pinos")
    with pytest.raises(InputError, match=r"console\.uart"):
        build_ports(broken)
    ok = with_platform(inputs_of("de2-115"), console="pinos")
    names = [p.name for p in build_ports(ok).ports]
    check(("UART_RXD" in names) and ("UART_TXD" in names))


def _clock(plan: ClockPlan, role: str) -> ClockRole:
    """Return a role of the plan, which must exist."""
    found = plan.get(role)
    check(found is not None, role)
    return cast(ClockRole, found)


def test_the_clock_plan_of_the_de0_cv() -> None:
    """The roles, in PLL order, are the four outputs of today's PLL."""
    plan = clock_plan(inputs_of("de0-cv"))
    check_equal(
        [c.role for c in plan.roles], ["mem", "mem_pin", "fetch", "core"]
    )
    check_equal(_clock(plan, "mem_pin").phase_ps, 4000)
    check_equal(_clock(plan, "core").phase_ps, 8250)
    check_equal(_clock(plan, "core").period_ns, Fraction(20))
    check_equal(plan.min_period_ns, Fraction(10))
    check_equal(plan.index("core"), 3)


def test_the_memory_clock_is_capped_by_the_chip() -> None:
    """V7: 150 MHz exceeds the 143 MHz of the chip."""
    inputs = inputs_of("de0-cv")
    clocks = dict(inputs.platform["clocks"]) | {"mem": {"mhz": 150}}
    broken = with_platform(inputs, clocks=clocks)
    with pytest.raises(InputError, match="exceeds chip IS42S16320D-7"):
        clock_plan(broken)


def test_an_unmeasured_phase_is_a_warning() -> None:
    """An unmeasured DRAM_CLK phase is zero, with a warning."""
    plan = clock_plan(inputs_of("de2-115"))
    check_equal(_clock(plan, "mem_pin").phase_ps, 0)
    check(plan.warnings)
