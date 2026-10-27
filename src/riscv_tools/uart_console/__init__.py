"""Read the program's output through the JTAG UART while it runs."""

from .core import decode_line, read_console

__all__ = ["decode_line", "read_console"]
