"""run_suite: the display follows each program number if asked."""

from pathlib import Path
from typing import Any, cast

import pytest

from riscv_tools import display
from riscv_tools.jtag import JtagLink
from riscv_tools.orchestrator import runner, suite


@pytest.mark.parametrize(
    "enabled, expected",
    [
        (True, [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0x10, 0x11]),
        (False, []),
    ],
)
def test_display_shows_the_number_of_each_program(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    enabled: bool,
    expected: list[int],
) -> None:
    """Display shows the number of each program."""
    writes: list[int] = []

    def write_display(_link: object, value: int) -> None:
        writes.append(value)

    flags: list[bool] = []

    def write_fail(_link: object, failed: bool) -> bool:
        flags.append(failed)
        return failed

    def run_one(
        _ctx: object,
        entry: dict[str, str],
        **_k: object,
    ) -> bool:
        return entry["name"] != "t3"

    monkeypatch.setattr(display, "write_display", write_display)
    monkeypatch.setattr(display, "write_fail", write_fail)
    monkeypatch.setattr(suite, "run_one", run_one)
    # eleven programs: the 10th and the 11th tell decimal from
    # hexadecimal
    manifest = [{"name": f"t{n}"} for n in range(1, 12)]
    cfg: dict[str, Any] = {"orchestrator": {"board_display": enabled}}
    ctx = runner.RunContext(
        cfg, cast(JtagLink, None), tmp_path, tmp_path, tmp_path
    )
    suite.run_suite(ctx, manifest, runner.SuiteOptions(reconfigure=False))
    assert writes == expected
    # cleared at the start, then set by the one program that fails
    assert flags == ([False, True] if enabled else [])
