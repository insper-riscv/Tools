"""The host side of the program's console: the JTAG UART of the platform.

A program prints through a UART whose other end is a Virtual JTAG instance (see
Memory's docs/EXTERNAL_BUS.md). This module scans it and hands the bytes to a
callback as they arrive, while the program runs. Pure mechanism, no policy.
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


def _forward_typed(source: TextIO, process: subprocess.Popen[str]) -> None:
    """Give each line the reader types to the script, as hex digits of its bytes."""
    stdin: IO[str] = process.stdin  # type: ignore[assignment]
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
    """Scan the UART, calling on_bytes with each chunk the program printed.

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
        An input whose lines are given to the program as they arrive (the
        keyboard of an interactive console); the console ends with it.

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
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if typed is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if typed is not None:
        threading.Thread(
            target=_forward_typed, args=(typed, process), daemon=True
        ).start()
    stdout: IO[str] = process.stdout  # type: ignore[assignment]
    try:
        for line in stdout:
            chunk = decode_line(line)
            if chunk:
                received += chunk
                on_bytes(chunk)
    except KeyboardInterrupt:
        process.terminate()
    finally:
        process.wait()
    if process.returncode not in (0, -15):
        error = process.stderr.read() if process.stderr else ""
        raise RuntimeError(f"uart_console.tcl failed ({process.returncode}): {error}")
    return bytes(received)
