"""Tests of the SoC generics of the top and of the merged PLL clocks."""

from pathlib import Path

from multifpga_support import BOARDS, CHIPS, platform_file
from support import check_equal, check_in, check_not_in

from riscv_tools.board_generate import Generated, GenerateRequest, generate

SWITCH_WINDOWS = """  SWITCHES:
    base: 0xD1000000
    size: 16
  KEYS:
    base: 0xD2000000
    size: 16
"""
FETCH_LINE = "  fetch: {mhz: 76.923077, phase_ps: 0}\n"
CORE_LINE = "  core:  {mhz: 76.923077, phase_ps: 7500}\n"


def _generate(
    tmp_path: Path, old: str = "peripherals:", new: str = "peripherals:"
) -> Generated:
    """Generate the de0-cv fixture with one text replaced."""
    text = platform_file("de0-cv").read_text(encoding="utf-8")
    check_in(old, text)
    target = tmp_path / "platform.yaml"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return generate(GenerateRequest(target, None, BOARDS, CHIPS, (), True))


def _file(result: Generated, suffix: str) -> str:
    """Return the text of the generated file with the suffix."""
    return next(t for n, t in result.files.items() if n.endswith(suffix))


def test_the_window_tables_are_cast_to_the_interconnect_type(
    tmp_path: Path,
) -> None:
    """The map package type is not the type the soc generic expects."""
    top = " ".join(_file(_generate(tmp_path), "_top.vhd").split())
    check_in(
        "periph_bases => work.interconnect_pkg.addr_array_t(PERIPH_BASES)",
        top,
    )
    check_in(
        "periph_masks => work.interconnect_pkg.addr_array_t(PERIPH_MASKS)",
        top,
    )


def test_the_plic_sources_have_the_floor_of_the_soc(tmp_path: Path) -> None:
    """The soc needs 6 sources at least, so the top gives a floor."""
    top = " ".join(_file(_generate(tmp_path), "_top.vhd").split())
    check_in(
        "plic_n_sources => work.interconnect_pkg.max_of(6, "
        "(0 => PLIC_N_SOURCES))",
        top,
    )


def test_switches_and_keys_need_a_window_in_the_platform(
    tmp_path: Path,
) -> None:
    """The board has the pins, but without a window there is no role."""
    top = " ".join(_file(_generate(tmp_path), "_top.vhd").split())
    check_in("has_switches => false", top)
    check_in("has_keys => false", top)
    check_not_in("switches_width", top)
    check_not_in("switches_index", top)


def test_switches_and_keys_with_a_window_are_wired(tmp_path: Path) -> None:
    """A platform that maps SWITCHES and KEYS gets both roles."""
    result = _generate(
        tmp_path, "peripherals:\n", "peripherals:\n" + SWITCH_WINDOWS
    )
    top = " ".join(_file(result, "_top.vhd").split())
    check_in("has_switches => true", top)
    check_in("has_keys => true", top)
    check_in("switches_index => SWITCHES_INDEX", top)
    check_in("keys_index => KEYS_INDEX", top)


def test_a_merged_pll_output_is_constrained_by_the_kept_node(
    tmp_path: Path,
) -> None:
    """Fetch and controller at the same rate and phase are one clock."""
    result = _generate(
        tmp_path, FETCH_LINE, "  fetch: {mhz: 100, phase_ps: 0}\n"
    )
    sdc = _file(result, ".sdc")
    check_not_in("general[2]", sdc)
    check_in("general[0].gpll", sdc)
    check_in("set clk_fetch {pll_inst|altera_pll_i|general[0]", sdc)
    check_in("set mem_core_clocks [get_clocks [list $clk_core]]", sdc)
    check_in("set_max_delay -from $mem_clocks -to $mem_core_clocks", sdc)


def test_distinct_phases_keep_each_output(tmp_path: Path) -> None:
    """Without a merge every output keeps its own node."""
    sdc = _file(_generate(tmp_path), ".sdc")
    check_in("general[2].gpll", sdc)
    check_in("set_max_delay -from $mem_clocks -to $core_clocks", sdc)
    check_equal(sdc.count("mem_core_clocks"), 0)
