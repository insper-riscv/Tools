"""Run a subprocess, streaming its output live and capturing it.

Shared by jtag.link.run and quartus_program.core._run_captured, so
that every Quartus call streams and captures its output the same way.
"""

import selectors
import subprocess
import sys
from typing import IO, Any, cast

# Popen options that run_streaming sets itself; a caller cannot override
# them.
_FORCED_KWARGS = ("stdout", "stderr", "text", "bufsize", "capture_output")


def run_streaming(
    cmd: list[str], **kw: Any
) -> subprocess.CompletedProcess[str]:
    """Run cmd, echoing and capturing its output as it arrives.

    Each line is echoed as it arrives, so a long compile does not look
    like a hang. A CalledProcessError raised here carries the real
    .stdout and .stderr text, which a caller can classify.

    Parameters
    ----------
    cmd : list of str
        The command and its arguments.
    **kw : Any
        Extra Popen options (for example cwd). stdout, stderr, text and
        bufsize are always set by this function.

    Returns
    -------
    subprocess.CompletedProcess
        With text .stdout and .stderr.

    Raises
    ------
    subprocess.CalledProcessError
        cmd exited non-zero.
    """
    print("+", " ".join(str(c) for c in cmd))
    for forced in _FORCED_KWARGS:
        kw.pop(forced, None)
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        **kw,
    ) as proc:
        stdout_text, stderr_text = _pump(proc)
        returncode = proc.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode, cmd, output=stdout_text, stderr=stderr_text
        )
    return subprocess.CompletedProcess(
        cmd, returncode, stdout_text, stderr_text
    )


def _pump(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Echo the output of proc as it arrives and return it.

    Parameters
    ----------
    proc : subprocess.Popen
        A process started with stdout and stderr piped, in text mode.

    Returns
    -------
    tuple of str
        The stdout and the stderr text.
    """
    # Statically Popen.stdout/.stderr are `IO[Any] | None`; both are
    # always real files here since the caller passed PIPE for each.
    proc_stdout = cast(IO[str], proc.stdout)
    proc_stderr = cast(IO[str], proc.stderr)
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    # key.data carries the actual file object alongside where to echo
    # and accumulate its lines; key.fileobj itself is typed as the
    # broader FileDescriptorLike (int | IO[Any] | ...) by selectors,
    # with no .readline(), so reading through it directly doesn't
    # type-check even though we know exactly what we registered.
    sel = selectors.DefaultSelector()
    sel.register(
        proc_stdout,
        selectors.EVENT_READ,
        (proc_stdout, sys.stdout, stdout_chunks),
    )
    sel.register(
        proc_stderr,
        selectors.EVENT_READ,
        (proc_stderr, sys.stderr, stderr_chunks),
    )
    open_streams = 2
    while open_streams > 0:
        for key, _ in sel.select():
            src, stream_out, chunks = key.data
            line = src.readline()
            if line == "":
                sel.unregister(src)
                open_streams -= 1
                continue
            stream_out.write(line)
            stream_out.flush()
            chunks.append(line)
    return "".join(stdout_chunks), "".join(stderr_chunks)
