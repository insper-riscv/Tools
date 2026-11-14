"""Tests for the roles of general use of `io` in the `board.yaml`."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from catalog_support import fresh_board, fresh_platform, write_catalog
from multifpga_support import inputs_of
from support import check_equal, check_in

from riscv_tools.board_ports import build_ports
from riscv_tools.board_schema import (
    Catalog,
    Pin,
    SchemaError,
    bracketed,
    parse_platform_fields,
    role_count,
    role_signals,
)

GPIO = ["GPIO_0[35:0]", "GPIO_1[35:0]"]


def _load(root: Path, roles: dict[str, Any]) -> Any:
    """Write a catalog whose board has the roles, and read the board."""
    board = fresh_board()
    board["io"] = board.get("io", {}) | roles
    write_catalog(root, board)
    return Catalog.for_root(root).load_board("bd")


def test_a_role_of_general_use_has_no_polarity_and_many_groups(
    tmp_path: Path,
) -> None:
    """`gpio` takes a list of groups and no `active`."""
    spec = _load(tmp_path, {"gpio": {"signals": GPIO, "bidirectional": True}})
    role = spec.io["gpio"]
    check_equal(role.all_groups, tuple(GPIO))
    check_equal((role.active, role.bidirectional), ("high", True))
    check_equal(role_count(role), 72)
    check_equal(role_signals(role)[36], "GPIO_1[0]")


def test_direction_inout_is_the_same_as_bidirectional(tmp_path: Path) -> None:
    """Either spelling asks for `inout` ports."""
    spec = _load(
        tmp_path, {"ex_io": {"signals": "EX_IO[6:0]", "direction": "inout"}}
    )
    check_equal(spec.io["ex_io"].bidirectional, True)
    check_equal(role_count(spec.io["ex_io"]), 7)


def test_the_green_leds_keep_their_polarity(tmp_path: Path) -> None:
    """`leds_green` is an output role: `active` is required."""
    spec = _load(
        tmp_path, {"leds_green": {"signals": "LEDG[8:0]", "active": "high"}}
    )
    check_equal(spec.io["leds_green"].active, "high")
    with pytest.raises(SchemaError, match="active"):
        _load(tmp_path / "other", {"leds_green": {"signals": "LEDG[8:0]"}})


def test_the_extra_clocks_are_scalars_in_a_list(tmp_path: Path) -> None:
    """`clock_extra` counts one unit per signal."""
    names = ["CLOCK2_50", "CLOCK3_50", "SMA_CLKIN", "SMA_CLKOUT"]
    spec = _load(tmp_path, {"clock_extra": {"signals": names}})
    check_equal(role_count(spec.io["clock_extra"]), 4)


def test_a_new_role_cannot_be_required_by_the_platform() -> None:
    """The roles of general use are optional on the platform side."""
    platform = fresh_platform()
    platform["io"] = {"gpio": {"count": 8, "need": "required"}}
    with pytest.raises(SchemaError, match="optional for a role"):
        parse_platform_fields(platform)
    platform["io"] = {"gpio": {"count": 8, "need": "optional"}}
    check_in("gpio", parse_platform_fields(platform).io)


def test_a_flat_pin_name_is_read_as_a_bit_of_a_bus() -> None:
    """`HSMC_CLKIN_N1` answers to `HSMC_CLKIN_N[1]`."""
    check_equal(bracketed("HSMC_CLKIN_N1"), "HSMC_CLKIN_N[1]")
    check_equal(bracketed("KEY[0]"), "KEY[0]")


def test_a_bidirectional_role_makes_inout_ports_in_list_order() -> None:
    """The ports of a role follow its groups and are `inout`."""
    base = inputs_of("de0-cv")
    signals = {
        f"{stem}[{i}]": Pin(f"{stem}[{i}]", "A1", "3.3-V", "inout", "manual")
        for stem in ("GPIO_0", "GPIO_1")
        for i in range(4)
    }
    board = dict(base.board)
    board["io"] = {
        "gpio": {
            "signals": "GPIO_0[3:0]",
            "active": "high",
            "groups": ["GPIO_0[3:0]", "GPIO_1[3:0]"],
            "bidirectional": True,
        }
    }
    platform = dict(base.platform)
    platform["io"] = {"gpio": {"count": 8, "need": "optional"}}
    inputs = replace(
        base, board=board, platform=platform, signals=base.signals | signals
    )
    ports = [p for p in build_ports(inputs).ports if p.role == "gpio"]
    check_equal([p.name for p in ports], ["GPIO_0", "GPIO_1"])
    check_equal({p.direction for p in ports}, {"inout"})
    check_equal(sum(p.width for p in ports), 8)
