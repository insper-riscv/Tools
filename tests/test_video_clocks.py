"""Tests of the pixel clock of the video and the clock pins."""

from fractions import Fraction
from pathlib import Path

import pytest
from peripherals_support import request
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_clocks import clock_plan
from riscv_tools.board_generate import Generated, generate
from riscv_tools.board_inputs import InputError, load_inputs
from riscv_tools.board_video import pixel_request, uses_pixel
from riscv_tools.memory_map import load_platform


def _file(result: Generated, suffix: str) -> str:
    """Give the text of the generated file that ends with a suffix."""
    return next(t for n, t in result.files.items() if n.endswith(suffix))


@pytest.mark.parametrize(
    ("kind", "entity"), [("video", "video"), ("hdmi", "hdmi_tx")]
)
def test_the_pixel_clock_reaches_the_pll_top_and_sdc(
    kind: str, entity: str, tmp_path: Path
) -> None:
    """The mode of the board makes the pixel output of the PLL."""
    result = generate(request(tmp_path, kind))
    top = " ".join(_file(result, "_top.vhd").split())
    check_in("signal clk_pixel : std_logic;", top)
    check_in("outclk_3 => clk_pixel", top)
    check_in(f"entity work.{entity}", top)
    check_in("i_pixel_clk => clk_pixel", top)
    check_equal([w for w in result.warnings if "pixel clock" in w], [])
    sdc = _file(result, ".sdc")
    check_in("set clk_pixel {", sdc)
    check_in("set_max_delay -from $video_clocks -to $core_clocks", sdc)
    check_in("25.000000", _file(result, "_pll.v"))


def test_a_platform_without_video_has_no_pixel_clock(tmp_path: Path) -> None:
    """The PLL and the `.sdc` keep only the clocks of the SoC."""
    result = generate(request(tmp_path, "ir"))
    check_not_in("clk_pixel", _file(result, "_top.vhd"))
    check_not_in("video_clocks", _file(result, ".sdc"))


def test_the_pixel_clock_is_its_own_domain(tmp_path: Path) -> None:
    """The pixel clock is out of the bound of the SoC crossings."""
    req = request(tmp_path, "video")
    inputs = load_inputs(
        req.platform_file, None, req.boards_dir, req.chips_dir
    )
    plain = clock_plan(inputs)
    fast = clock_plan(inputs, Fraction(148), True)
    check_equal([c.role for c in fast.video_roles], ["pixel", "pixel_x5"])
    x5 = fast.get("pixel_x5")
    check_equal(x5.mhz if x5 else None, 5 * 148)
    check_equal(fast.min_period_ns, plain.min_period_ns)
    check_equal(plain.video_roles, ())


def test_the_pixel_clock_comes_from_the_mode_or_the_kind(
    tmp_path: Path,
) -> None:
    """A written `pixel_clock_khz` must agree with the mode."""
    req = request(tmp_path, "hdmi")
    platform = load_platform(req.platform_file)
    check(uses_pixel(platform))
    check_equal(pixel_request(platform, None), None)
    for item in platform["peripherals"]:
        if item["name"] == "HDMI":
            item["pixel_clock_khz"] = 25000
    found = pixel_request(platform, None)
    check_equal(found.mhz if found else None, Fraction(25))


def test_a_pixel_clock_that_disagrees_with_the_mode_is_refused(
    tmp_path: Path,
) -> None:
    """The kind and the mode ask for different clocks."""
    req = request(tmp_path, "hdmi")
    text = req.platform_file.read_text(encoding="utf-8")
    req.platform_file.write_text(
        text.replace(
            "kind: hdmi, base: 0x80200000",
            "kind: hdmi, base: 0x80200000, pixel_clock_khz: 74250",
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="pixel_clock_khz 74250 differs"):
        generate(req)


def test_a_pixel_clock_the_pll_cannot_make_stops_the_generation(
    tmp_path: Path,
) -> None:
    """The refusal comes as an input error, not as a traceback."""
    req = request(tmp_path, "hdmi")
    text = req.platform_file.read_text(encoding="utf-8")
    req.platform_file.write_text(
        text.replace(
            "kind: hdmi, base: 0x80200000",
            "kind: hdmi, base: 0x80200000, pixel_clock_khz: 7777777",
        ).replace("io:\n", "io:\n  video: {outside_manual: true}\n", 1),
        encoding="utf-8",
    )
    with pytest.raises(InputError):
        generate(req)


def test_the_tmds_kind_asks_the_pll_for_the_serial_clock(
    tmp_path: Path,
) -> None:
    """The PLL makes `pixel` and `pixel_x5`, the `.sdc` pairs them."""
    result = generate(request(tmp_path, "hdmi_tmds"))
    top = " ".join(_file(result, "_top.vhd").split())
    check_in("signal clk_pixel, clk_pixel_x5 : std_logic;", top)
    check_in("i_serial_clk => clk_pixel_x5", top)
    sdc = _file(result, ".sdc")
    check_in("set clk_pixel_x5 {", sdc)
    check_in(
        "set video_clocks [get_clocks [list $clk_pixel $clk_pixel_x5]]", sdc
    )
    check_in("set_max_delay -from $video_clocks -to $core_clocks", sdc)
