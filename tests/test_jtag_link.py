"""The JTAG link: its command line and the SDRAM debug instance."""

from typing import Any

import pytest
from support import check_equal

from riscv_tools.cli.common import jtag_link
from riscv_tools.jtag import JtagLink, link


class FakeRun:
    """Stands for run: records the command and the environment."""

    def __init__(self) -> None:
        """Start with no call."""
        self.cmd: list[str] = []
        self.env: dict[str, str] = {}

    def __call__(self, cmd: list[str], **kw: Any) -> object:
        """Record the call."""
        self.cmd = cmd
        self.env = kw["env"]
        return object()


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    """Replace run of the link module."""
    fake = FakeRun()
    monkeypatch.setattr(link, "run", fake)
    return fake


def test_the_debug_instance_defaults_to_zero(fake_run: FakeRun) -> None:
    """A link without an instance runs the script on instance 0."""
    link.run_tcl(JtagLink("cable", "chip"), "sdram_dbg.tcl", "read", 0, 1)
    check_equal(fake_run.env["RV32_SDRAM_DEBUG_INSTANCE"], "0", "instance")
    check_equal(fake_run.cmd[-5:], ["cable", "chip", "read", "0", "1"], "args")


def test_the_debug_instance_reaches_the_script(fake_run: FakeRun) -> None:
    """The index of the link goes to the script in the environment."""
    link.run_tcl(JtagLink("cable", "chip", 3), "sdram_dbg.tcl", "read", 0, 1)
    check_equal(fake_run.env["RV32_SDRAM_DEBUG_INSTANCE"], "3", "instance")


def test_the_config_gives_the_instance_to_the_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """quartus.sdram_debug_instance becomes the sdram_instance field."""
    monkeypatch.setattr(
        "riscv_tools.cli.common.detect_jtag_hardware", lambda: "cable"
    )
    cfg = {"quartus": {"jtag_device": "chip", "sdram_debug_instance": 3}}
    made = jtag_link(cfg)
    check_equal(made.sdram_instance, 3, "sdram_instance")
