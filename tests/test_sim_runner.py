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
FIXTURES_LIB = Path(__file__).resolve().parent / "fixtures" / "sim_lib"
# cocotb_tools.runner's subprocess inherits PYTHONPATH from *this*
# process' sys.path (see cocotb_tools.runner.Simulator._set_env), so
# test_module below can use bare names ("test_pass") once this is on
# sys.path — no __init__.py/dotted-package plumbing needed.
sys.path.insert(0, str(FIXTURES))
sys.path.insert(0, str(FIXTURES_LIB))


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


def test_sim_runner_parameters_reach_ghdl(tmp_path: Path, dummy_hex: Path) -> None:
    # dut.vhd's CYCLES generic defaults to 5 (test_pass passes well
    # within its own 20-cycle poll loop). Overriding it to 50 via
    # `parameters` must make the same otherwise-passing test fail —
    # if `parameters` weren't actually reaching GHDL's `-g` (e.g. sat
    # in .build() instead of .test(), which GHDL silently ignores),
    # CYCLES would stay at its default and this would wrongly pass.
    passed = sim_runner.run_test(
        toplevel="dut",
        vhdl_sources=[str(FIXTURES / "dut.vhd")],
        ghdl_std="08",
        test_module="test_pass",
        hex_path=dummy_hex,
        test_name="test_pass_slow",
        build_dir=tmp_path / "params_build",
        parameters={"CYCLES": "50"},
    )
    assert passed is False


def _run_lib_test(
    tmp_path: Path,
    dummy_hex: Path,
    *,
    flags: list[str],
    with_data: bool = True,
    expected: int = 43,
) -> bool:
    data = tmp_path / "value.txt"
    data.write_text("42\n")
    libraries_dir = tmp_path / "libraries"
    sim_runner.build_libraries(
        {"helper": [str(FIXTURES_LIB / "helper.vhd")]}, "08", flags, libraries_dir
    )
    return sim_runner.run_test(
        toplevel="dut",
        vhdl_sources=[str(FIXTURES_LIB / "dut.vhd")],
        ghdl_std="08",
        test_module="test_lib",
        hex_path=dummy_hex,
        test_name="test_lib",
        build_dir=tmp_path / "lib_build",
        ghdl_flags=flags,
        libraries_dir=libraries_dir,
        run_files={"data.txt": data} if with_data else {},
        extra_env={"EXPECTED": str(expected)},
    )


def test_sim_runner_libraries_flags_run_files_and_env(
    tmp_path: Path, dummy_hex: Path
) -> None:
    # 42 comes from data.txt, copied into the run directory; +1 from
    # helper.bump, in a library analyzed separately and found by -P;
    # the library only analyzes with -fsynopsys; EXPECTED reaches the
    # cocotb module as an environment variable.
    assert _run_lib_test(tmp_path, dummy_hex, flags=["-fsynopsys"]) is True


def test_sim_runner_env_reaches_the_test_module(
    tmp_path: Path, dummy_hex: Path
) -> None:
    assert (
        _run_lib_test(tmp_path, dummy_hex, flags=["-fsynopsys"], expected=99) is False
    )


def test_build_libraries_needs_the_flags_the_library_needs(tmp_path: Path) -> None:
    import subprocess  # noqa: PLC0415

    with pytest.raises(subprocess.CalledProcessError):
        sim_runner.build_libraries(
            {"helper": [str(FIXTURES_LIB / "helper.vhd")]},
            "08",
            [],
            tmp_path / "libraries",
        )


def test_expand_env_replaces_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_TEST_DIR", "/opt/quartus")

    assert sim_runner.expand_env("$SIM_TEST_DIR/eda") == "/opt/quartus/eda"
    assert sim_runner.expand_env("${SIM_TEST_DIR}/eda") == "/opt/quartus/eda"


def test_expand_env_rejects_an_unset_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIM_TEST_UNSET", raising=False)

    with pytest.raises(SystemExit, match="SIM_TEST_UNSET"):
        sim_runner.expand_env("$SIM_TEST_UNSET/eda")
