"""End-to-end test of sim_runner.run_test against a real GHDL install.

Uses the "sim" extra (cocotb + cocotb-tools) — proves the whole chain
(GHDL build via cocotb_tools.runner -> simulate -> parse results.xml)
actually works, for both a passing and a failing cocotb test (see
fixtures/sim_min/).

Skipped automatically if either tool isn't available.
"""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

from riscv_tools import sim_runner

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sim_min"
# cocotb_tools.runner's subprocess inherits PYTHONPATH from *this*
# process' sys.path (see cocotb_tools.runner.Simulator._set_env), so
# test_module below can use bare names ("test_pass") once this is on
# sys.path — no __init__.py/dotted-package plumbing needed.
sys.path.insert(0, str(FIXTURES))


def _have_cocotb() -> bool:
    try:
        importlib.import_module("cocotb_tools.runner")
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    shutil.which("ghdl") is None or not _have_cocotb(),
    reason="needs ghdl on PATH and the 'sim' extra (cocotb) installed",
)


@pytest.fixture
def dummy_hex(tmp_path: Path) -> Path:
    hex_path = tmp_path / "dummy.hex"
    hex_path.write_text("00000000\n")
    return hex_path


def test_sim_runner_reports_pass(tmp_path: Path, dummy_hex: Path) -> None:
    passed = sim_runner.run_test(
        toplevel="dut",
        vhdl_sources=[str(FIXTURES / "dut.vhd")],
        ghdl_std="08",
        test_module="test_pass",
        hex_path=dummy_hex,
        test_name="test_pass",
        build_dir=tmp_path / "pass_build",
    )
    assert passed is True


def test_sim_runner_reports_fail(tmp_path: Path, dummy_hex: Path) -> None:
    passed = sim_runner.run_test(
        toplevel="dut",
        vhdl_sources=[str(FIXTURES / "dut.vhd")],
        ghdl_std="08",
        test_module="test_fail",
        hex_path=dummy_hex,
        test_name="test_fail",
        build_dir=tmp_path / "fail_build",
    )
    assert passed is False
