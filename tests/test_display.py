"""display: the pieces that need no board."""

from typing import cast

import pytest

from riscv_tools import display
from riscv_tools.jtag import JtagLink


def test_state_packs_the_index_and_the_state():
    assert display.encode_state(0x2A, display.STATE_PASSED) == 0x2A0001
    assert display.encode_state(0, display.STATE_RUNNING) == 0
    assert display.encode_state(0xFF, display.STATE_FAILED) == 0xFF000F


@pytest.mark.parametrize("index, state", [(256, 0), (-1, 0), (0, 0x10000), (0, -1)])
def test_state_rejects_values_that_do_not_fit(index: int, state: int) -> None:
    with pytest.raises(ValueError, match="does not fit"):
        display.encode_state(index, state)


def test_value_is_the_last_value_line():
    out = "Info: x\nVALUE=000001\nInfo: y\nVALUE=2a000f\n"
    assert display.decode_value(out) == 0x2A000F


def test_output_without_a_value_is_an_error():
    with pytest.raises(RuntimeError, match="no value"):
        display.decode_value("Info: nothing\n")


def test_write_rejects_a_value_over_24_bits():
    with pytest.raises(ValueError, match="24 bits"):
        display.write_display(cast(JtagLink, None), 1 << 24)
