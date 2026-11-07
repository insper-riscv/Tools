"""Tests for board_inputs (the catalog read by board_schema)."""

import pytest
from multifpga_support import BOARD_NAMES, BOARDS, CHIPS, inputs_of
from support import check, check_equal, check_in

from riscv_tools.board_inputs import (
    InputError,
    load_inputs,
    resolve_board_name,
)


def test_the_six_boards_load() -> None:
    """Each board of the fixtures loads with its family and pins."""
    for name in BOARD_NAMES:
        inputs = inputs_of(name)
        check_equal(inputs.board["board"], name)
        check_in("pll", inputs.family)
        check(inputs.signals)


def test_a_chip_inherits_from_its_parent() -> None:
    """`extends` brings the parent's timing and keeps own fields."""
    chip = inputs_of("de2-115").chips["IS42S16320B-7"]
    check_equal(chip["timing"]["trcd_ps"], 15000)
    check_equal(chip["chip"], "IS42S16320B-7")
    small = inputs_of("mkr-vidor-4000").chips["AS4C4M16SA-7BCN"]
    check_equal(small["organization"]["row_bits"], 12)
    check_equal(small["timing"]["tck_ps"], 7000)


def test_only_the_chips_with_timings_are_loaded() -> None:
    """The EPCS64 of the DE0-Nano has no timing to load."""
    check_equal(list(inputs_of("de0-nano").chips), ["IS42S16160B-7"])


def test_the_board_name_comes_from_the_platform() -> None:
    """The command line wins, then `board`, then a single `boards`."""
    check_equal(
        resolve_board_name({"board": "auto", "boards": ["x"]}, None), "x"
    )
    check_equal(resolve_board_name({"board": "y"}, None), "y")
    check_equal(resolve_board_name({"board": "y"}, "z"), "z")
    with pytest.raises(InputError, match="--board"):
        resolve_board_name({"board": "auto", "boards": ["a", "b"]}, None)


def test_an_unknown_board_lists_the_known_ones() -> None:
    """V1: the message names the board and the known ones."""
    with pytest.raises(InputError, match=r"de2-116.*known: \['de0-cv"):
        load_inputs(
            BOARDS.parent / "platforms" / "de0-cv.yaml",
            "de2-116",
            BOARDS,
            CHIPS,
        )
