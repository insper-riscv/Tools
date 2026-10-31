"""display: the pieces that need no board."""

from typing import cast

import pytest

from riscv_tools import display
from riscv_tools.jtag import JtagLink


def test_act_number_is_ac_then_four_decimal_digits():
    """Act number is ac then four decimal digits."""
    assert display.encode_act(1) == 0xAC0001
    assert display.encode_act(59) == 0xAC0059
    assert display.encode_act(9999) == 0xAC9999


def test_own_test_number_uses_the_six_digits_in_decimal():
    """Own test number uses the six digits in decimal."""
    assert display.encode_test(1) == 0x000001
    assert display.encode_test(10) == 0x000010
    assert display.encode_test(999999) == 0x999999


@pytest.mark.parametrize("number", [0, -1, 10000])
def test_act_number_rejects_what_does_not_fit(number: int) -> None:
    """Act number rejects what does not fit."""
    with pytest.raises(ValueError, match="not between"):
        display.encode_act(number)


@pytest.mark.parametrize("number", [0, -1, 1000000])
def test_own_test_number_rejects_what_does_not_fit(number: int) -> None:
    """Own test number rejects what does not fit."""
    with pytest.raises(ValueError, match="not between"):
        display.encode_test(number)


def test_value_is_the_last_value_line():
    """Value is the last value line."""
    out = "Info: x\nVALUE=000001\nInfo: y\nVALUE=2a000f\n"
    assert display.decode_value(out) == 0x2A000F


def test_output_without_a_value_is_an_error():
    """Output without a value is an error."""
    with pytest.raises(RuntimeError, match="no value"):
        display.decode_value("Info: nothing\n")


def test_write_rejects_a_value_over_24_bits():
    """Write rejects a value over 24 bits."""
    with pytest.raises(ValueError, match="24 bits"):
        display.write_display(cast(JtagLink, None), 1 << 24)


def test_fail_flag_is_read_from_the_flag_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail flag is read from the flag line."""

    class Done:
        returncode = 0
        stdout = "Info: x\nFLAG=1\n"
        stderr = ""

    def fake_run(*_a: object, **_k: object) -> Done:
        return Done()

    monkeypatch.setattr("riscv_tools.display.core.subprocess.run", fake_run)
    link = cast(
        JtagLink, type("L", (), {"hardware_name": "h", "device_name": "d"})()
    )
    assert display.read_fail(link) is True
    assert (
        display.write_fail(link, False) is True
    )  # the stub always answers FLAG=1
