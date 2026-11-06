"""Tests for board_generate and the generators it composes."""

import shutil
import subprocess
from pathlib import Path

import pytest
from multifpga_support import (
    BOARD_NAMES,
    generated,
)
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_generate import write_project
from riscv_tools.pll_generator import (
    PllIpPendingError,
    RenderedPll,
    register_renderer,
)
from riscv_tools.pll_generator import core as pll_core

ALTPLL_BOARDS = ("de2-115", "de0-nano", "de10-lite", "mkr-vidor-4000")


def _fake_altpll(module: str, solution: pll_core.PllSolution) -> RenderedPll:
    """Write a placeholder altpll file for the extension-point tests."""
    return RenderedPll(module, ".v", f"// altpll {solution.vco_mhz}\n", ())


def test_the_de0_cv_project_has_every_file() -> None:
    """Top, PLL, SDC, project and chip package are produced."""
    result = generated("de0-cv")
    check_equal(
        sorted(result.files),
        [
            "chip_is42s16320d_7_pkg.vhd",
            "de0_cv_de0_cv.qpf",
            "de0_cv_de0_cv.qsf",
            "de0_cv_de0_cv.sdc",
            "de0_cv_de0_cv_pll.v",
            "de0_cv_de0_cv_top.vhd",
        ],
    )
    check_equal(result.folder, "de0-cv-de0-cv")


def test_the_qsf_lists_family_device_and_generated_sources() -> None:
    """The project carries the family text, the device and its files."""
    qsf = generated("de0-cv").files["de0_cv_de0_cv.qsf"]
    check_in('FAMILY "Cyclone V"', qsf)
    check_in("DEVICE 5CEBA4F23C7", qsf)
    check_in("TOP_LEVEL_ENTITY de0_cv_de0_cv_top", qsf)
    check_in("SDC_FILE de0_cv_de0_cv.sdc", qsf)
    check_in("VERILOG_FILE de0_cv_de0_cv_pll.v", qsf)
    check_in("VHDL_FILE chip_is42s16320d_7_pkg.vhd", qsf)
    check_in("PLL_COMPENSATION_MODE DIRECT", qsf)


def test_the_top_only_connects() -> None:
    """The DE0-CV top wires PLL, SoC, backends and the ring."""
    top = generated("de0-cv").files["de0_cv_de0_cv_top.vhd"]
    check_in("entity de0_cv_de0_cv_top is", top)
    check_in("HPM_COUNTERS : natural range 0 to 29 := 29;", top)
    check_in("pll_inst : entity work.de0_cv_de0_cv_pll", top)
    check_in("soc_inst : entity work.soc", top)
    check_in("FIRST_LATENCY => 24", top)
    check_in("NEXT_LATENCY => 4", top)
    check_in("SIZE_BYTES => 258048", top)
    check_in("tristate_buffer_1bit", top)
    check_in("DRAM_DQ(i)", top)
    check_in("HEX5 <= not soc_display(41 downto 35);", top)
    check_in("reset_active <= not FPGA_RESET_N;", top)
    check_in("DRAM_CLK <= clk_mem_pin;", top)
    check_not_in("0x", top)


def test_the_top_is_valid_vhdl_syntax(tmp_path: Path) -> None:
    """GHDL accepts the syntax of every generated top."""
    ghdl = shutil.which("ghdl")
    if ghdl is None:
        pytest.skip("ghdl not installed")
    names = [*BOARD_NAMES]
    register_renderer("altpll", _fake_altpll)
    try:
        for name in names:
            top = next(
                t
                for n, t in generated(name).files.items()
                if n.endswith("_top.vhd")
            )
            source = tmp_path / f"{name}_top.vhd"
            source.write_text(top)
            done = subprocess.run(
                [ghdl, "-s", "--std=08", str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            # As entidades do SoC e dos backends ainda não estão no
            # espaço de trabalho: só os erros de sintaxe contam.
            errors = [
                line
                for line in (done.stdout + done.stderr).splitlines()
                if "error" in line and "not found in library" not in line
            ]
            check_equal(errors, [], name)
    finally:
        del pll_core.RENDERERS["altpll"]


@pytest.mark.parametrize("board", ["de0-cv", "de10-nano"])
def test_cyclone_v_boards_generate_with_altera_pll(board: str) -> None:
    """The two altera_pll boards generate end to end."""
    result = generated(board)
    check_in(
        "altera_pll",
        next(t for n, t in result.files.items() if n.endswith("_pll.v")),
    )


@pytest.mark.parametrize("board", ALTPLL_BOARDS)
def test_altpll_boards_wait_for_their_renderer(board: str) -> None:
    """Until measured, the error names the extension point."""
    with pytest.raises(PllIpPendingError, match="register_renderer"):
        generated(board)


@pytest.mark.parametrize("board", ALTPLL_BOARDS)
def test_altpll_boards_generate_once_a_renderer_exists(board: str) -> None:
    """With a renderer the project of the other boards builds."""
    register_renderer("altpll", _fake_altpll)
    try:
        result = generated(board)
    finally:
        del pll_core.RENDERERS["altpll"]
    qsf = next(t for n, t in result.files.items() if n.endswith(".qsf"))
    check_in("set_location_assignment", qsf)
    sdc = next(t for n, t in result.files.items() if n.endswith(".sdc"))
    check_in("derive_pll_clocks", sdc)


def test_the_de2_115_uses_a_burst_of_one_and_its_flash_chip() -> None:
    """Two x16 chips make a 32-bit bus; the NOR has its own package."""
    register_renderer("altpll", _fake_altpll)
    try:
        result = generated("de2-115")
    finally:
        del pll_core.RENDERERS["altpll"]
    sdram = result.files["chip_is42s16320b_7_pkg.vhd"]
    check_in('"0000000110000"', sdram)
    check_in("chip_s29gl064n90_pkg.vhd", result.files)
    check_in("DQ_WIDTH => 32", result.files["de2_115_de2_115_top.vhd"])


def test_the_de0_cv_needs_no_inferred_pin() -> None:
    """The pins the DE0-CV top uses are all confirmed."""
    result = generated("de0-cv", accept=False)
    check(result.files)


def test_the_files_are_written_under_the_project_folder(
    tmp_path: Path,
) -> None:
    """write_project creates `<platform>-<board>` under the output."""
    folder = write_project(tmp_path, generated("de0-cv"))
    check_equal(folder, tmp_path / "de0-cv-de0-cv")
    check((folder / "de0_cv_de0_cv.sdc").is_file())


def test_the_generation_is_deterministic() -> None:
    """Two runs give the same text."""
    check_equal(generated("de0-cv").files, generated("de0-cv").files)
