"""Tests of the SRAM backend of the generated top."""

from fractions import Fraction
from pathlib import Path

from multifpga_support import (
    BOARDS,
    CHIPS,
    platform_file,
)
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_clocks import ClockPlan
from riscv_tools.board_generate import GenerateRequest, generate
from riscv_tools.top_generator.spec import TopSpec
from riscv_tools.top_generator.sram import sram_backend


def _sram_platform(tmp_path: Path) -> Path:
    """Write the DE2-115 platform with the RAM in the SRAM chip."""
    text = platform_file("de2-115").read_text(encoding="utf-8")
    text = text.replace("type: sdram", "type: sram").replace(
        "size: 128M", "size: 2M"
    )
    target = tmp_path / "platform.yaml"
    target.write_text(text, encoding="utf-8")
    return target


def _generate(tmp_path: Path) -> tuple[str, str, list[str]]:
    """Generate the SRAM top; give the top, the SDC and the warnings."""
    result = generate(
        GenerateRequest(
            _sram_platform(tmp_path),
            None,
            BOARDS,
            CHIPS,
            accept_inferred=True,
        )
    )
    top = next(t for n, t in result.files.items() if n.endswith("_top.vhd"))
    sdc = next(t for n, t in result.files.items() if n.endswith(".sdc"))
    return " ".join(top.split()), sdc, result.warnings


def test_the_sram_ram_gets_the_controller_and_its_pins(
    tmp_path: Path,
) -> None:
    """The data port reaches the chip pins through `sram_ctrl`."""
    top, _, warnings = _generate(tmp_path)
    check_equal([w for w in warnings if "no entity" in w], [])
    check_in("sram_ctrl_inst : entity work.sram_ctrl", top)
    for pin in (
        "o_sram_addr => SRAM_ADDR",
        "o_sram_ce_n => SRAM_CE_N",
        "o_sram_oe_n => SRAM_OE_N",
        "o_sram_we_n => SRAM_WE_N",
        "o_sram_lb_n => SRAM_LB_N",
        "o_sram_ub_n => SRAM_UB_N",
    ):
        check_in(pin, top)
    check_in("base_kib => RAM_BASE_KIB mod 65536", top)
    check_in("i_advance => rd_adv", top)
    check_in("o_d => SRAM_DQ(i)", top)
    check_in("sram_dq_in <= SRAM_DQ;", top)
    check_not_in("sdram_ctrl_inst", top)


def test_the_sram_size_comes_from_the_chip_package(tmp_path: Path) -> None:
    """The window of the chip is the size of its package."""
    top, _, _ = _generate(tmp_path)
    check_in("size_bytes => work.chip_is61wv102416bll_10_pkg.SIZE_BYTES", top)


def test_the_sram_pins_are_free_of_timing_requirements(
    tmp_path: Path,
) -> None:
    """The controller counts the cycles of the chip: false paths."""
    _, sdc, _ = _generate(tmp_path)
    check_in("set_false_path -from [get_ports {SRAM_DQ[*]}]", sdc)
    check_in("set_false_path -to   [get_ports {SRAM_ADDR[*]}]", sdc)


def test_a_board_without_the_sram_pins_warns_and_leaves_the_ram_idle() -> None:
    """Missing pins give no instance and a warning."""
    plan = ClockPlan("CLOCK_50", Fraction(50), ())
    spec = TopSpec({}, plan, (), "pll", "top", {})
    notes: list[str] = []
    signals, body = sram_backend(spec, notes)
    check_equal(signals, [])
    check_equal(body, "")
    check(len(notes) == 1 and "no SRAM backend" in notes[0])
