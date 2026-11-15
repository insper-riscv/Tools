"""Read and write the SDRAM through its JTAG debug port."""

from riscv_tools.sdram_debug.core import (
    fill,
    load_words,
    read_words,
    write_word,
)
from riscv_tools.sdram_debug.stream import (
    Capabilities,
    StreamError,
    capabilities,
    crc32,
    decode_capabilities,
    set_hold,
    stream_read,
    stream_write,
)

__all__ = [
    "Capabilities",
    "StreamError",
    "capabilities",
    "crc32",
    "decode_capabilities",
    "fill",
    "load_words",
    "read_words",
    "set_hold",
    "stream_read",
    "stream_write",
    "write_word",
]
