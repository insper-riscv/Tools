"""The lock of a board, held for a session with its owner recorded.

One lock file per board, taken with `flock`. It is the same file the
agents and the runner of the Tests already take with the `flock`
command (`/tmp/de0cv-<host>.lock`), so every user of a board waits for
the others. The holder writes who it is into the file, to be shown to
whoever finds the board busy.
"""

import fcntl
import getpass
import json
import os
import socket
import sys
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from riscv_tools.board.errors import BoardBusyError

DEFAULT_WAIT_S = 4 * 3600
POLL_S = 5.0


@dataclass(frozen=True)
class LockOwner:
    """Who holds a lock, as written in the lock file.

    Attributes
    ----------
    host : str
        The machine.
    user : str
        The user.
    pid : int
        The process.
    command : str
        Its command line.
    since : str
        When it took the lock, UTC ISO 8601.
    """

    host: str
    user: str
    pid: int
    command: str
    since: str


def current_owner() -> LockOwner:
    """Describe this process as a lock owner.

    Returns
    -------
    LockOwner
        This process.
    """
    return LockOwner(
        socket.gethostname(),
        getpass.getuser(),
        os.getpid(),
        " ".join(sys.argv),
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def read_owner(path: Path) -> LockOwner | None:
    """Read the owner recorded in a lock file.

    Parameters
    ----------
    path : Path
        The lock file.

    Returns
    -------
    LockOwner or None
        The owner, or None when the file is empty, absent, or written
        by another program (a plain `flock` records nothing).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LockOwner(**data)
    except OSError, ValueError, TypeError:
        return None


def _open(path: Path) -> int:
    """Open the lock file, read-only when it is not writable."""
    try:
        return os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    except PermissionError:
        return os.open(path, os.O_RDONLY)


def is_free(path: Path) -> bool:
    """Tell whether nobody holds the lock right now.

    Parameters
    ----------
    path : Path
        The lock file.

    Returns
    -------
    bool
        True when the lock could be taken (and was let go at once).
    """
    if not path.exists() and not path.parent.is_dir():
        return True
    fd = _open(path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(fd)
    return True


class BoardLock:
    """The exclusive lock of one board, as a context manager."""

    def __init__(
        self,
        path: Path,
        wait_s: float = 0,
        poll_s: float = POLL_S,
    ) -> None:
        """Prepare the lock; nothing is taken until `acquire`.

        Parameters
        ----------
        path : Path
            The lock file.
        wait_s : float
            How long to wait for a busy lock; 0 fails at once.
        poll_s : float
            The pause between tries.
        """
        self.path = path
        self.wait_s = wait_s
        self.poll_s = poll_s
        self._fd: int | None = None

    def acquire(self) -> None:
        """Take the lock and record this process as its owner.

        Raises
        ------
        BoardBusyError
            The lock stayed busy for the whole wait; the message names
            the owner.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = _open(self.path)
        deadline = time.monotonic() + self.wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise BoardBusyError(self._busy_message()) from None
                time.sleep(self.poll_s)
        self._fd = fd
        self._record()

    def _record(self) -> None:
        """Write the owner into the file, when it is writable."""
        if self._fd is None:
            return
        try:
            os.ftruncate(self._fd, 0)
            text = json.dumps(asdict(current_owner())).encode()
            os.pwrite(self._fd, text, 0)
        except OSError:
            return

    def _busy_message(self) -> str:
        """Say who holds the lock."""
        owner = read_owner(self.path)
        who = (
            f"{owner.user}@{owner.host} (pid {owner.pid}, since "
            f"{owner.since}): {owner.command}"
            if owner
            else "an owner that did not record itself (a plain flock)"
        )
        return f"lock {self.path} is busy, held by {who}"

    def release(self) -> None:
        """Clear the owner and let the lock go."""
        if self._fd is None:
            return
        with suppress(OSError):
            os.ftruncate(self._fd, 0)
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> Self:
        """Take the lock.

        Returns
        -------
        BoardLock
            This lock, held.
        """
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Let the lock go."""
        self.release()
