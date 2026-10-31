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
    """Run cmd, echoing it and streaming stdout/stderr as they arrive.

    Used instead of a plain subprocess.run(capture_output=True) for the
    slow Quartus tools, for two reasons:

    - Visibility: each line is echoed as it arrives, so a compile that
      runs for minutes does not look like a hang. Both pipes are read
      with selectors (POSIX only).
    - Classification: a CalledProcessError raised here always carries
      the real .stdout and .stderr text (for example "Can't scan JTAG
      chain"), which a caller can classify.

    The number of processes launched for cmd does not change; callers
    that need two commands in one shell process build that into cmd.

    Parameters
    ----------
    cmd : list of str
        Argument list to execute (same shape as subprocess.run's
        first argument).
    **kw : Any
        Extra keyword arguments forwarded to subprocess.Popen (e.g.
        cwd). stdout/stderr/text/bufsize are always forced regardless
        of what's passed here.

    Returns
    -------
    subprocess.CompletedProcess
        .stdout/.stderr are always text (never None).

    Raises
    ------
    subprocess.CalledProcessError
        cmd exited non-zero; .stdout/.stderr populated same as above.
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
    """Echo the output of proc as it arrives and collect it.

    Parameters
    ----------
    proc : subprocess.Popen
        A process started with stdout=PIPE, stderr=PIPE and text=True.

    Returns
    -------
    tuple of str
        Everything proc wrote to stdout and to stderr.
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
