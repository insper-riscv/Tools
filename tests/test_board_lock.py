"""The lock of a board: exclusion, owner record, and the legacy file."""

import json
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from support import check_equal

from riscv_tools.board import BoardBusyError, BoardLock
from riscv_tools.board.lock import is_free, read_owner

HOLDER = (
    "import fcntl,sys,time;f=open(sys.argv[1],'a');"
    "fcntl.flock(f,fcntl.LOCK_EX);print('held',flush=True);time.sleep(30)"
)


def test_the_lock_records_its_owner_and_clears_it(tmp_path: Path) -> None:
    """While held, the file names the owner; afterwards it is empty."""
    path = tmp_path / "de0cv-ws.lock"
    with BoardLock(path):
        owner = read_owner(path)
        if owner is None:
            pytest.fail("no owner recorded")
        check_equal(owner.pid > 0, True, "pid")
        check_equal(is_free(path), False, "held")
    check_equal(read_owner(path), None, "cleared")
    check_equal(is_free(path), True, "free")


def test_a_second_taker_fails_naming_the_owner(tmp_path: Path) -> None:
    """A busy lock raises BoardBusyError with the recorded owner."""
    path = tmp_path / "board.lock"
    with (
        BoardLock(path),
        pytest.raises(BoardBusyError, match="held by") as raised,
    ):
        BoardLock(path).acquire()
    check_equal(raised.value.case, 9, "case")


@contextmanager
def plain_flock_holder(path: Path, seconds: int) -> Generator[None]:
    """Hold the lock file with a plain flock, as the agents do."""
    code = HOLDER.replace("time.sleep(30)", f"time.sleep({seconds})")
    with subprocess.Popen(
        [sys.executable, "-c", code, str(path)],
        stdout=subprocess.PIPE,
        text=True,
    ) as holder:
        if holder.stdout is None:
            pytest.fail("no pipe")
        holder.stdout.readline()
        try:
            yield
        finally:
            holder.kill()


def test_a_plain_flock_holder_is_respected(tmp_path: Path) -> None:
    """A plain `flock` of the agents blocks the lock too."""
    path = tmp_path / "de0cv-laptop.lock"
    with plain_flock_holder(path, 30):
        with pytest.raises(BoardBusyError, match="did not record itself"):
            BoardLock(path).acquire()
        check_equal(is_free(path), False, "busy")
    check_equal(is_free(path), True, "free after the holder died")


def test_the_wait_ends_when_the_lock_is_released(tmp_path: Path) -> None:
    """With a wait, the taker gets the lock once the holder lets go."""
    path = tmp_path / "board.lock"
    with plain_flock_holder(path, 1), BoardLock(path, wait_s=10, poll_s=0.2):
        written = json.loads(path.read_text())
        check_equal(written["pid"] > 0, True, "taken after the wait")
