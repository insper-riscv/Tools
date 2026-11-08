"""The JTAG link: its command line and the SDRAM debug instance."""

from typing import Any

import pytest
from support import check_equal

from riscv_tools.cli.common import jtag_link
from riscv_tools.jtag import JtagLink, detect_jtag_hardware, link
from riscv_tools.jtag.hardware import idcode_of


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

    def cable(_device: str, _forced: str | None) -> str:
        return "cable"

    monkeypatch.setattr("riscv_tools.cli.common.detect_jtag_hardware", cable)
    cfg = {"quartus": {"jtag_device": "chip", "sdram_debug_instance": 3}}
    made = jtag_link(cfg)
    check_equal(made.sdram_instance, 3, "sdram_instance")


JTAGCONFIG = """1) USB-Blaster [1-2]
  02B050DD   5CE(BA4|FA4)

2) USB-Blaster [1-3]
  020F70DD   10CL120(Y|Z)/EP3C120/..

3) USB-Blaster [1-6]
  031050DD   10M50DA(.|ES)/10M50DC
"""


def _fake_jtagconfig(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make jtagconfig print three cables."""

    def run(*_a: object, **_k: object) -> object:
        return type("Done", (), {"stdout": JTAGCONFIG})()

    monkeypatch.setattr("riscv_tools.jtag.hardware.subprocess.run", run)


def test_the_cable_is_chosen_by_the_idcode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cable that lists the IDCODE of the project chip is taken."""
    _fake_jtagconfig(monkeypatch)
    check_equal(
        detect_jtag_hardware("@1: 10M50DA(.|ES)/10M50DC (0x031050DD)"),
        "USB-Blaster [1-6]",
        "cable",
    )


def test_without_a_match_the_first_cable_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No device, or an IDCODE no cable lists, gives the first cable."""
    _fake_jtagconfig(monkeypatch)
    check_equal(detect_jtag_hardware(), "USB-Blaster [1-2]", "no device")
    check_equal(
        detect_jtag_hardware("chip (0x12345678)"),
        "USB-Blaster [1-2]",
        "no match",
    )


def test_the_idcode_of_a_device_name() -> None:
    """The IDCODE comes out in upper case, or None."""
    check_equal(idcode_of("@1: x (0x02b050dd)"), "02B050DD", "idcode")
    check_equal(idcode_of("chip"), None, "none")


def test_a_forced_cable_must_list_the_idcode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--cable keeps the cable, and the IDCODE is still checked."""
    _fake_jtagconfig(monkeypatch)
    check_equal(
        detect_jtag_hardware("x (0x020F70DD)", "USB-Blaster [1-3]"),
        "USB-Blaster [1-3]",
        "forced",
    )
    with pytest.raises(RuntimeError, match="does not list the IDCODE"):
        detect_jtag_hardware("x (0x02B050DD)", "USB-Blaster [1-3]")
    with pytest.raises(RuntimeError, match="not listed"):
        detect_jtag_hardware("x (0x02B050DD)", "USB-Blaster [9-9]")
