"""Tests for chip_package."""

from pathlib import Path
from typing import Any

import pytest
from multifpga_support import CHIPS
from support import check_equal, check_in, check_not_in

from riscv_tools.board_inputs import InputError, chip_view
from riscv_tools.board_schema import Catalog
from riscv_tools.chip_package import (
    chip_io_delays,
    package_name,
    render_chip_package,
)


def load_chip(chips: Path, name: str) -> dict[str, Any]:
    """Read a chip of the catalog as the generators see it."""
    return chip_view(Catalog(chips, chips).load_chip(name))


def test_the_package_name_is_a_vhdl_identifier() -> None:
    """Dashes become underscores and the case is lowered."""
    check_equal(package_name("IS42S16320D-7"), "chip_is42s16320d_7_pkg")


def test_the_timings_are_those_of_the_handwritten_package() -> None:
    """The names and values are those of today's sdram_pkg.vhd."""
    text = render_chip_package(load_chip(CHIPS, "IS42S16320D-7"))
    for line in (
        "constant T_CK_PS : natural := 7000;",
        "constant T_RCD_PS : natural := 15000;",
        "constant T_RP_PS : natural := 15000;",
        "constant T_RAS_PS : natural := 42000;",
        "constant T_RC_PS : natural := 60000;",
        "constant T_RFC_PS : natural := 63000;",
        "constant T_WR_PS : natural := 14000;",
        "constant T_MRD_CK : natural := 2;",
        "constant T_INIT_PS : natural := 200_000_000;",
        "constant T_REFI_PS : natural := 7_812_500;",
        "constant INIT_REFRESHES : natural := 8;",
        "constant CAS_LATENCY : natural := 3;",
    ):
        check_in(line, " ".join(text.split()).replace("  ", " "))
    check_in('"0000000110001"', text)
    check_in("package chip_is42s16320d_7_pkg is", text)


def test_the_mode_register_follows_the_burst() -> None:
    """A 32-bit bus (two chips) has burst 1: the register changes."""
    chip = load_chip(CHIPS, "IS42S16320B-7")
    check_in('"0000000110000"', render_chip_package(chip, 1))
    check_in('"0000000110010"', render_chip_package(chip, 4))


def test_the_organization_gives_the_widths() -> None:
    """Row, column and bank bits come from the organization."""
    text = render_chip_package(load_chip(CHIPS, "AS4C4M16SA-7BCN"))
    check_in("ROW_BITS : natural := 12;", " ".join(text.split()))
    check_in("COL_BITS : natural := 8;", " ".join(text.split()))
    check_in("BANK_BITS : natural := 2;", " ".join(text.split()))


def test_a_nor_chip_has_no_sdram_constants() -> None:
    """The NOR package carries its timings and not the mode register."""
    text = render_chip_package(load_chip(CHIPS, "S29GL064N90"))
    check_in("ACCESS_NS", text)
    check_in("PAGE_ACCESS_NS", text)
    check_in("SECTOR_BYTES : natural := 65536", " ".join(text.split()))
    check_not_in("MODE_REG", text)


def test_an_sdram_without_a_timing_is_refused() -> None:
    """A missing tRCD fails with the name of the chip."""
    chip = load_chip(CHIPS, "IS42S16320D-7")
    del chip["timing"]["trcd_ps"]
    with pytest.raises(InputError, match="trcd_ps"):
        render_chip_package(chip)


def test_the_io_delays_are_those_of_the_handwritten_sdc() -> None:
    """Output 1.5 and -0.8 ns, input 5.4 and 2.5 ns."""
    delays = chip_io_delays(load_chip(CHIPS, "IS42S16320D-7"))
    check_equal(
        (
            delays.output_max_ns,
            delays.output_min_ns,
            delays.input_max_ns,
            delays.input_min_ns,
        ),
        (1.5, -0.8, 5.4, 2.5),
    )
