"""Tests for freq_sweep."""

import argparse
from pathlib import Path
from typing import Any

import pytest

from riscv_tools import cli, orchestrator
from riscv_tools.cli import tools_cmd
from riscv_tools.freq_sweep import PllParams, set_pll_freq

THREE_PHASE_PLL = """\
altpll_component : altpll
    port map (
        clk => sub_wire0);
altpll_component.output_clock_frequency0("10.000000 MHz");
altpll_component.phase_shift0("0 ps");
altpll_component.output_clock_frequency1("10.000000 MHz");
altpll_component.phase_shift1("33333 ps");
altpll_component.output_clock_frequency2("10.000000 MHz");
altpll_component.phase_shift2("66667 ps");
"""


def test_set_pll_freq_rewrites_frequency_and_phases(tmp_path: Path) -> None:
    """Set pll freq rewrites frequency and phases."""
    pll_file = tmp_path / "pll.v"
    pll_file.write_text(THREE_PHASE_PLL)

    set_pll_freq(
        pll_file,
        20.0,
        PllParams(
            phase_count=3,
            freq_param_template="output_clock_frequency{idx}",
            phase_param_template="phase_shift{idx}",
            freq_unit="MHz",
            phase_unit="ps",
        ),
    )

    text = pll_file.read_text()
    period_ps = round(1_000_000 / 20.0)
    assert '.output_clock_frequency0("20.000000 MHz")' in text
    assert '.output_clock_frequency1("20.000000 MHz")' in text
    assert '.output_clock_frequency2("20.000000 MHz")' in text
    assert '.phase_shift0("0 ps")' in text
    assert f'.phase_shift1("{period_ps // 3} ps")' in text
    assert f'.phase_shift2("{(2 * period_ps) // 3} ps")' in text
    # Unrelated lines must be left untouched.
    assert "altpll_component : altpll" in text


def test_set_pll_freq_single_phase_default(tmp_path: Path) -> None:
    """Set pll freq single phase default."""
    pll_file = tmp_path / "pll.v"
    pll_file.write_text('.output_clock_frequency0("10.000000 MHz");\n')

    set_pll_freq(
        pll_file,
        50.0,
        PllParams(
            phase_count=1,
            freq_param_template="output_clock_frequency{idx}",
            phase_param_template="phase_shift{idx}",
            freq_unit="MHz",
            phase_unit="ps",
        ),
    )

    assert '.output_clock_frequency0("50.000000 MHz")' in pll_file.read_text()


def test_set_pll_freq_missing_param_left_unchanged(tmp_path: Path) -> None:
    # phase_count set higher than what the file actually declares,
    # the nonexistent pair should be silently skipped, not raise.
    """Set pll freq missing param left unchanged."""
    pll_file = tmp_path / "pll.v"
    original = (
        '.output_clock_frequency0("10.000000 MHz");\n.phase_shift0("0 ps");\n'
    )
    pll_file.write_text(original)

    set_pll_freq(
        pll_file,
        15.0,
        PllParams(
            phase_count=3,
            freq_param_template="output_clock_frequency{idx}",
            phase_param_template="phase_shift{idx}",
            freq_unit="MHz",
            phase_unit="ps",
        ),
    )

    text = pll_file.read_text()
    assert '.output_clock_frequency0("15.000000 MHz")' in text
    assert "output_clock_frequency1" not in text
    assert "output_clock_frequency2" not in text


def test_set_pll_freq_custom_param_template(tmp_path: Path) -> None:
    """Set pll freq custom param template."""
    pll_file = tmp_path / "pll.vhd"
    pll_file.write_text('.clkout_freq0("100.000000 kHz");\n')

    set_pll_freq(
        pll_file,
        200.0,
        PllParams(
            phase_count=1,
            freq_param_template="clkout_freq{idx}",
            phase_param_template="clkout_phase{idx}",
            freq_unit="kHz",
            phase_unit="fs",
        ),
    )

    assert '.clkout_freq0("200.000000 kHz")' in pll_file.read_text()


def test_cmd_freq_sweep_resolves_pll_file_against_the_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cmd freq sweep resolves pll file against the project root."""
    seen: dict[str, Any] = {}

    def fake_linear(job: Any, *_: Any) -> list[dict[str, Any]]:
        seen["pll_file"] = job.cfg["freq_sweep"]["pll_file"]
        return [{"freq_mhz": 10.0, "status": "pass"}]

    cfg = {
        "quartus": {"project_dir": "q"},
        "paths": {"build_dir": "build"},
        "freq_sweep": {"pll_file": "../src/pll.v"},
    }

    def fake_load_config(_path: str) -> dict[str, Any]:
        return cfg

    def fake_link(_cfg: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(tools_cmd, "load_config", fake_load_config)
    monkeypatch.setattr(tools_cmd, "jtag_link", fake_link)
    monkeypatch.setattr(orchestrator, "run_freq_sweep_linear", fake_linear)

    args = argparse.Namespace(
        config="unused",
        root=str(tmp_path),
        mif="a.mif",
        golden="g.json",
        binary=False,
        start=1.0,
        stop=2.0,
        step=1.0,
        out=None,
    )
    cli.cmd_freq_sweep(args)

    assert seen["pll_file"] == str(tmp_path / "../src/pll.v")
