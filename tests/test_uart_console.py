"""The JTAG UART console: script line decoding and its process."""

import io
import time
from typing import Any, override

import pytest

from riscv_tools import uart_console
from riscv_tools.jtag import JtagLink
from riscv_tools.uart_console import core

LINK = JtagLink(hardware_name="cable", device_name="device")


class FakeProcess:
    """Stands for quartus_stp: prints the given lines, then exits."""

    def __init__(
        self, lines: list[str], returncode: int = 0, stderr: str = ""
    ) -> None:
        """Feed the given lines to stdout and stderr, then exit."""
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.stderr = io.StringIO(stderr)
        self.returncode = returncode
        self.cmd: list[str] = []

    stdin = io.StringIO()

    def wait(self) -> int:
        """Return the exit code."""
        return self.returncode

    def terminate(self) -> None:
        """Nothing to stop."""


def _popen(fake: FakeProcess, monkeypatch: pytest.MonkeyPatch) -> None:
    def popen(cmd: list[str], **_kw: Any) -> FakeProcess:
        fake.cmd = cmd
        return fake

    monkeypatch.setattr(core.subprocess, "Popen", popen)


def test_decode_line_reads_data_lines_only() -> None:
    """Decode line reads data lines only."""
    assert uart_console.decode_line("BYTES=68656c6c6f") == b"hello"
    assert uart_console.decode_line("  BYTES=0a\n") == b"\n"
    assert uart_console.decode_line("info: Quartus Prime") is None
    assert uart_console.decode_line("") is None


def test_read_console_delivers_the_chunks_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read console delivers the chunks in order."""
    fake = FakeProcess(["info: opening", "BYTES=6865", "BYTES=6c6c6f0a"])
    _popen(fake, monkeypatch)
    chunks: list[bytes] = []
    got = uart_console.read_console(LINK, chunks.append, seconds=5)
    assert chunks == [b"he", b"llo\n"]
    assert got == b"hello\n"
    assert fake.cmd[-3:] == ["cable", "device", "5"]


def test_read_console_passes_the_bytes_to_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read console passes the bytes to send."""
    fake = FakeProcess([])
    _popen(fake, monkeypatch)
    uart_console.read_console(LINK, lambda _c: None, send=b"hi")
    assert fake.cmd[-1] == "6869"


def test_read_console_reports_a_failed_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read console reports a failed script."""
    _popen(
        FakeProcess([], returncode=2, stderr="cannot open the UART"),
        monkeypatch,
    )
    with pytest.raises(RuntimeError, match="cannot open the UART"):
        uart_console.read_console(LINK, lambda _c: None)


def test_interactive_console_gives_the_typed_lines_to_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interactive console gives the typed lines to the script."""
    fake = FakeProcess(["BYTES=6f6b0a"])
    fake.stdin = _KeepOpen()
    _popen(fake, monkeypatch)
    received: list[bytes] = []
    typed = io.StringIO("peek 40000000\nquit\n")

    got = uart_console.read_console(LINK, received.append, typed=typed)

    assert fake.cmd[-1] == "-"
    assert got == b"ok\n"
    # the lines are forwarded by a thread: give it the time it needs
    for _ in range(100):
        if fake.stdin.closed_with is not None:
            break
        time.sleep(0.01)
    assert fake.stdin.closed_with == (
        b"peek 40000000\n".hex() + "\n" + b"quit\n".hex() + "\n"
    )


class _KeepOpen(io.StringIO):
    """A stdin whose content survives close(), for the test to read."""

    closed_with: str | None = None

    @override
    def close(self) -> None:
        self.closed_with = self.getvalue()
        super().close()
