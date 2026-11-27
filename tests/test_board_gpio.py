"""Expansion GPIO connects MMIO to physical board pins."""

from dataclasses import replace
from typing import Any

import pytest
from multifpga_support import inputs_of
from support import check, check_equal, check_in

from riscv_tools.board_clocks import clock_plan
from riscv_tools.board_inputs import InputError
from riscv_tools.board_ports import build_ports
from riscv_tools.memory_map.external import vhdl_lines
from riscv_tools.top_generator.external import external_top
from riscv_tools.top_generator.spec import TopSpec


def make_spec(
    groups: list[list[int]] | None = None,
    second: list[list[int]] | None = None,
) -> TopSpec:
    """Build a four-pin expansion role from the board fixture."""
    inputs = inputs_of("de0-cv")
    item: dict[str, Any] = {
        "name": "MOTOR",
        "kind": "gpio",
        "roles": ["gpio"],
        "base": 0x80001000,
        "size": 128,
        "groups": groups or [[0, 2], [1, 3]],
    }
    peripherals = [*inputs.platform["peripherals"], item]
    if second is not None:
        peripherals.append(
            {**item, "name": "SECOND", "base": 0x80001200, "groups": second}
        )
    board = {
        **inputs.board,
        "io": {
            **inputs.board["io"],
            "gpio": {
                "groups": ["GPIO_0[3:0]"],
                "signals": "GPIO_0[3:0]",
                "bidirectional": True,
            },
        },
    }
    signals = dict(inputs.signals)
    for i in range(4):
        signals[f"GPIO_0[{i}]"] = replace(
            signals[f"SW[{i}]"], name=f"GPIO_0[{i}]", direction="inout"
        )
    inputs = replace(
        inputs,
        board=board,
        signals=signals,
        platform={**inputs.platform, "peripherals": peripherals},
    )
    ports = build_ports(inputs).ports
    return TopSpec(
        inputs.platform, clock_plan(inputs), ports, "pll", "top", {}
    )


def test_board_exports_expansion_ports_and_register_bank() -> None:
    """The register bank must drive physical GPIO ports."""
    spec = make_spec()
    check(
        any(p.name == "GPIO_0" and p.direction == "inout" for p in spec.ports)
    )
    top = external_top(spec)
    body = "\n".join(top.body)
    check_in("entity work.gpio", body)
    check_in('group_sizes => x"0202"', body)
    check_in('group_members => x"03010200"', body)
    check_in("io_gpio_pins(3 downto 0) => GPIO_0", body)
    check_in("ext_we(MOTOR_EXT_POS)", body)
    check_in(
        "ext_rdata(32 * MOTOR_EXT_POS + 31 downto 32 * MOTOR_EXT_POS)", body
    )
    check_in("ext_addr_width => 5", top.generics)
    check_in("MOTOR_INDEX", vhdl_lines(spec.platform))
    check_in("MOTOR_EXT_POS", vhdl_lines(spec.platform))


def test_out_of_range_pin_is_rejected() -> None:
    """A group cannot point to an unimplemented physical pin."""
    with pytest.raises(InputError, match="invalid groups"):
        external_top(make_spec([[4]]))


def test_duplicate_pin_between_blocks_is_rejected() -> None:
    """Two banks cannot drive the same physical pin."""
    with pytest.raises(InputError, match="same physical pin"):
        external_top(make_spec([[0, 1]], [[1, 2]]))


def test_disjoint_banks_share_one_physical_port_without_duplicate_ports() -> (
    None
):
    """Disjoint MMIO banks share one physical port declaration."""
    spec = make_spec([[0, 1]], [[2, 3]])
    check_equal(sum(p.name == "GPIO_0" for p in spec.ports), 1)
    body = "\n".join(external_top(spec).body)
    check_in("motor_gpio_inst", body)
    check_in("second_gpio_inst", body)
    check_in("ext_we(SECOND_EXT_POS)", body)
