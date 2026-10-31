"""The host side of the program's console: the platform JTAG UART.

A program prints through a UART whose other end is a Virtual JTAG
instance (see Memory's docs/EXTERNAL_BUS.md). This module scans it and
hands the bytes to a callback as they arrive, while the program runs.
Pure mechanism, no policy.
"""

import contextlib
import subprocess
import threading
from collections.abc import Callable
from typing import IO, TextIO

from riscv_tools.jtag import JtagLink
from riscv_tools.jtag.link import TCL_DIR

BYTES_PREFIX = "BYTES="


def decode_line(line: str) -> bytes | None:
    """Decode one output line of the script.

    Parameters
    ----------
    line : str
        One line the script printed.

    Returns
    -------
    bytes or None
        The decoded bytes of a ``BYTES=<hex digits>`` line, else None.
    """
    line = line.strip()
    if not line.startswith(BYTES_PREFIX):
        return None
    return bytes.fromhex(line[len(BYTES_PREFIX) :])


def _pipe(stream: IO[str] | None) -> IO[str]:
    """Return a pipe that Popen was asked to create.

    Parameters
    ----------
    stream : IO of str or None
        The `stdin` or `stdout` attribute of the process.

    Returns
    -------
    IO of str
        The same stream.

    Raises
    ------
    RuntimeError
        The process has no such pipe.
    """
    if stream is None:
        raise RuntimeError("the uart_console process has no such pipe")
    return stream


def _forward_typed(source: TextIO, stdin: IO[str]) -> None:
    """Give each typed line to the script as hex digits of its bytes."""
    try:
        for line in source:
            stdin.write(line.encode().hex() + "\n")
            stdin.flush()
    except BrokenPipeError, ValueError:
        return
    finally:
        with contextlib.suppress(BrokenPipeError, ValueError):
            stdin.close()


def read_console(
    link: JtagLink,
    on_bytes: Callable[[bytes], None],
    seconds: float = 0,
    send: bytes = b"",
    *,
    typed: TextIO | None = None,
) -> bytes:
    """Scan the UART, calling on_bytes with each chunk printed.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    on_bytes : callable
        Called with each chunk as it arrives.
    seconds : float, optional
        How long to listen; 0 (the default) listens until interrupted.
    send : bytes, optional
        Bytes to give to the program, one per scan, at the start.
    typed : TextIO, optional
        An input whose lines are given to the program as they arrive
        (the keyboard of an interactive console); the console ends with
        it.

    Returns
    -------
    bytes
        Everything that was read.

    Raises
    ------
    RuntimeError
        The script exited with an error.
    """
    cmd = [
        "quartus_stp",
        "-t",
        str(TCL_DIR / "uart_console.tcl"),
        link.hardware_name,
        link.device_name,
        str(seconds),
    ]
    if typed is not None:
        cmd.append("-")
    elif send:
        cmd.append(send.hex())
    received = bytearray()
    with subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if typed is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        if typed is not None:
            threading.Thread(
                target=_forward_typed,
                args=(typed, _pipe(process.stdin)),
                daemon=True,
            ).start()
        try:
            for line in _pipe(process.stdout):
                chunk = decode_line(line)
                if chunk:
                    received += chunk
                    on_bytes(chunk)
        except KeyboardInterrupt:
            process.terminate()
        returncode = process.wait()
        error = process.stderr.read() if process.stderr else ""
    if returncode not in (0, -15):
        raise RuntimeError(f"uart_console.tcl failed ({returncode}): {error}")
    return bytes(received)
