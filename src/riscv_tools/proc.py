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

    Every caller in this project that shells out to a slow or
    frequently-invoked real-world tool (quartus_sh, quartus_pgm,
    quartus_stp) uses this instead of a plain
    subprocess.run(capture_output=True), for two reasons at once:

    - Visibility: capture_output blocks until the whole process exits
      before printing anything, fine for something that returns in
      under a second, indistinguishable from hanging for something
      that can run for minutes (a full compile) or that happens dozens
      of times in a test suite (each JTAG quartus_stp call). This
      reads both pipes via selectors (POSIX-only, fine; this project
      doesn't run on Windows) and echoes each line as it arrives.
    - Classification: a subprocess.CalledProcessError raised from here
      always carries real .stdout/.stderr text (e.g. "Can't scan JTAG
      chain") that a caller can classify (see
      orchestrator.runner._is_hardware_failure), unlike the None/None
      that a plain `subprocess.run(cmd, check=True)` leaves on its
      exception.

    Does NOT change how many processes get launched for a given cmd;
    callers that need to keep two commands in one shell process (see
    HARDWARE_PROGRAMMING.md: quartus_sh --flow compile and quartus_pgm
    must stay chained in a single `bash -c "cmd1 && cmd2"`, never two
    separate subprocess calls) build that into cmd themselves; this
    only changes how the one resulting process's own output is read.

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
