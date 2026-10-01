import sys
from pathlib import Path

import pytest

from riscv_tools import sim_runner


def test_extend_python_path_adds_the_root_relative_entries_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "path", ["/already"])
    (tmp_path / "platform").mkdir()
    sim_runner.extend_python_path(tmp_path, [".", "platform", "platform"])
    assert sys.path == [
        str((tmp_path / "platform").resolve()),
        str(tmp_path.resolve()),
        "/already",
    ]
