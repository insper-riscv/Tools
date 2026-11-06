"""Tests for board_inputs."""

from pathlib import Path

import pytest
from multifpga_support import BOARD_NAMES, BOARDS, CHIPS, inputs_of
from support import check, check_equal, check_in

from riscv_tools.board_inputs import (
    InputError,
    board_idcode,
    load_chip,
    load_inputs,
    resolve_board_name,
)


def test_the_six_boards_load() -> None:
    """Each board of the fixtures loads with its family and chips."""
    for name in BOARD_NAMES:
        inputs = inputs_of(name)
        check_equal(inputs.board["board"], name)
        check_in("pll", inputs.family)
        check(inputs.signals)


def test_a_chip_inherits_from_its_parent() -> None:
    """`extends` brings the parent's timing and keeps own fields."""
    chip = load_chip(CHIPS, "IS42S16320B-7")
    check_equal(chip["timing"]["trcd_ps"], 15000)
    check_equal(chip["source"], "inferido")
    check_equal(chip["chip"], "IS42S16320B-7")
    small = load_chip(CHIPS, "AS4C4M16SA-7BCN")
    check_equal(small["organization"]["row_bits"], 12)
    check_equal(small["timing"]["tck_ps"], 7000)


def test_an_extends_cycle_is_refused(tmp_path: Path) -> None:
    """Two chips that extend each other fail."""
    (tmp_path / "a.yaml").write_text("chip: a\nextends: b\n")
    (tmp_path / "b.yaml").write_text("chip: b\nextends: a\n")
    with pytest.raises(InputError, match="cycle"):
        load_chip(tmp_path, "a")


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


def test_the_idcode_is_the_one_of_the_fpga() -> None:
    """The cable is chosen by the IDCODE of the `fpga: true` entry."""
    check_equal(board_idcode(BOARDS, "de0-cv"), "02B050DD")
    check_equal(board_idcode(BOARDS, "de2-115"), "020F70DD")
