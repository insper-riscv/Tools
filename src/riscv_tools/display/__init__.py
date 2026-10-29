"""Host side of the seven-segment display register."""

from riscv_tools.display.core import (
    check_display,
    decode_value,
    encode_act,
    encode_test,
    read_display,
    read_fail,
    write_display,
    write_fail,
)

__all__ = [
    "check_display",
    "decode_value",
    "encode_act",
    "encode_test",
    "read_display",
    "read_fail",
    "write_display",
    "write_fail",
]
