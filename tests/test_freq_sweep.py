from pathlib import Path

from riscv_tools.freq_sweep import get_pll_freq, set_pll_freq

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
    pll_file = tmp_path / "pll.v"
    pll_file.write_text(THREE_PHASE_PLL)

    set_pll_freq(
        pll_file=pll_file,
        mhz=20.0,
        phase_count=3,
        freq_param_template="output_clock_frequency{idx}",
        phase_param_template="phase_shift{idx}",
        freq_unit="MHz",
        phase_unit="ps",
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
    pll_file = tmp_path / "pll.v"
    pll_file.write_text('.output_clock_frequency0("10.000000 MHz");\n')

    set_pll_freq(
        pll_file=pll_file,
        mhz=50.0,
        phase_count=1,
        freq_param_template="output_clock_frequency{idx}",
        phase_param_template="phase_shift{idx}",
        freq_unit="MHz",
        phase_unit="ps",
    )

    assert '.output_clock_frequency0("50.000000 MHz")' in pll_file.read_text()


def test_set_pll_freq_missing_param_left_unchanged(tmp_path: Path) -> None:
    # phase_count set higher than what the file actually declares —
    # the nonexistent pair should be silently skipped, not raise.
    pll_file = tmp_path / "pll.v"
    original = '.output_clock_frequency0("10.000000 MHz");\n.phase_shift0("0 ps");\n'
    pll_file.write_text(original)

    set_pll_freq(
        pll_file=pll_file,
        mhz=15.0,
        phase_count=3,
        freq_param_template="output_clock_frequency{idx}",
        phase_param_template="phase_shift{idx}",
        freq_unit="MHz",
        phase_unit="ps",
    )

    text = pll_file.read_text()
    assert '.output_clock_frequency0("15.000000 MHz")' in text
    assert "output_clock_frequency1" not in text
    assert "output_clock_frequency2" not in text


def test_set_pll_freq_custom_param_template(tmp_path: Path) -> None:
    pll_file = tmp_path / "pll.vhd"
    pll_file.write_text('.clkout_freq0("100.000000 kHz");\n')

    set_pll_freq(
        pll_file=pll_file,
        mhz=200.0,
        phase_count=1,
        freq_param_template="clkout_freq{idx}",
        phase_param_template="clkout_phase{idx}",
        freq_unit="kHz",
        phase_unit="fs",
    )

    assert '.clkout_freq0("200.000000 kHz")' in pll_file.read_text()


def test_get_pll_freq_reads_phase_zero(tmp_path: Path) -> None:
    pll_file = tmp_path / "pll.v"
    pll_file.write_text(THREE_PHASE_PLL)

    assert get_pll_freq(pll_file, "output_clock_frequency{idx}", "MHz") == 10.0


def test_get_pll_freq_returns_none_when_absent(tmp_path: Path) -> None:
    pll_file = tmp_path / "pll.v"
    pll_file.write_text("-- nothing relevant here\n")

    assert get_pll_freq(pll_file, "output_clock_frequency{idx}", "MHz") is None


def test_set_then_get_pll_freq_round_trips(tmp_path: Path) -> None:
    pll_file = tmp_path / "pll.v"
    pll_file.write_text(THREE_PHASE_PLL)

    set_pll_freq(
        pll_file=pll_file,
        mhz=33.5,
        phase_count=3,
        freq_param_template="output_clock_frequency{idx}",
        phase_param_template="phase_shift{idx}",
        freq_unit="MHz",
        phase_unit="ps",
    )

    assert get_pll_freq(pll_file, "output_clock_frequency{idx}", "MHz") == 33.5
