"""Tests for board_generate and the generators it composes."""

import shutil
import subprocess
from pathlib import Path

import pytest
from multifpga_support import BOARD_NAMES, generated
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_generate import write_project

CYCLONE_V = ("de0-cv", "de10-nano")
ALTPLL_BOARDS = ("de2-115", "de0-nano", "de10-lite", "mkr-vidor-4000")


def _top(name: str) -> str:
    """Return the generated top of a board."""
    files = generated(name).files
    return next(t for n, t in files.items() if n.endswith("_top.vhd"))


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
    check_equal(result.warnings, [])


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


def test_the_top_uses_the_real_entities_of_the_soc_and_memory() -> None:
    """The DE0-CV top wires the soc and the Memory backends by name."""
    top = _top("de0-cv")
    for fragment in (
        "entity de0_cv_de0_cv_top is",
        "use work.de0_cv_map_pkg.all;",
        "component de0_cv_de0_cv_pll is",
        "pll_inst : de0_cv_de0_cv_pll",
        "soc_inst : entity work.soc",
        "boot_inst : entity work.boot_memory",
        "flash_chip_inst : entity work.flash_chip",
        "first_latency => 24, next_latency => 4",
        "flash_loader_inst : entity work.flash_loader",
        "flash_jtag_inst : entity work.flash_jtag_shell",
        "sdram_data_bridge : entity work.sdram_cpu_bridge",
        "sdram_arbiter_inst : entity work.sdram_arbiter",
        "sdram_ctrl_inst : entity work.sdram_ctrl",
        "work.chip_is42s16320d_7_pkg.T_INIT_PS, 10000",
        "dq_tri : entity work.tristate_buffer_1bit",
        "o_d => DRAM_DQ(i)",
        "HEX5 <= display_hex(41 downto 35);",
        "reset_active <= not FPGA_RESET_N;",
        "DRAM_CLK <= clk_mem_pin;",
        "DRAM_LDQM <= dqm(0);",
        "io_switches => SW",
        "i_uart_tck => uart_tck",
        "instance_index => 1",
        "soc_rst <= rst_sr(1) or flash_halt;",
        "HPM_COUNTERS : natural range 0 to 29 := 29;",
    ):
        check_in(fragment, " ".join(top.split()))
    check_not_in("0x", top)


def test_the_soc_generics_come_from_the_map_package() -> None:
    """Map, caches and extensions are package constants."""
    top = " ".join(_top("de0-cv").split())
    for fragment in (
        "boot_memory_size_bytes => BOOT_MEMORY_SIZE_BYTES",
        "rom_end_kib => ROM_END_KIB",
        "icache_size_bits => ICACHE_SIZE_BITS",
        "has_zihpm => HAS_ZIHPM",
        "clint_tick_cycles => CLINT_TICK_CYCLES",
        "plic_n_sources => PLIC_N_SOURCES",
        "plic_addr_width => PLIC_ADDR_WIDTH",
        "switches_active_low => false",
        "keys_active_low => true",
        "display_active_low => true",
        "display_digits => 6",
        "uart_jtag_id => 4",
    ):
        check_in(fragment, top)


def test_a_platform_without_interrupts_never_reads_the_plic_package() -> None:
    """The PLIC and CLINT constants are always emitted, as literals."""
    top = " ".join(_top("de10-nano").split())
    check_in("plic_n_sources => 6", top)
    check_in("plic_addr_width => 20", top)
    check_in("clint_tick_cycles => 1", top)
    check_not_in("PLIC_", top)
    check_not_in("IRQ_", top)


def test_an_emulated_ram_gets_the_block_backend() -> None:
    """The emulated RAM is the on-chip port over a block RAM."""
    top = " ".join(_top("de10-nano").split())
    check_in("ram_port_inst : entity work.onchip_ram_port", top)
    check_in("ram_store_inst : entity work.ram", top)
    check_in("flash_chip_inst : entity work.flash_chip", top)


def test_a_backend_without_an_entity_warns_and_stays_idle() -> None:
    """NOR and a 32-bit SDRAM have no entity: warnings, no instance."""
    result = generated("de2-115")
    text = " ".join(result.warnings)
    check_in("region rom: backend dispositivo nor has no entity", text)
    check_in("sdram data width 32 needs the generalized sdram_ctrl", text)
    top = " ".join(_top("de2-115").split())
    check_not_in("sdram_ctrl_inst", top)
    check_not_in("entity work.device_backend", top)


def test_the_top_is_valid_vhdl_syntax(tmp_path: Path) -> None:
    """GHDL accepts the syntax of every generated top."""
    ghdl = shutil.which("ghdl")
    if ghdl is None:
        pytest.skip("ghdl not installed")
    for name in BOARD_NAMES:
        source = tmp_path / f"{name}_top.vhd"
        source.write_text(_top(name))
        done = subprocess.run(
            [ghdl, "-s", "--std=08", str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        # Os pacotes e as entidades do projeto não estão no espaço de
        # trabalho: só os erros de sintaxe contam.
        errors = [
            line
            for line in (done.stdout + done.stderr).splitlines()
            if "error" in line
            and "not found in library" not in line
            and "no unit" not in line
            and "was not analysed" not in line
        ]
        check_equal(errors, [], name)


@pytest.mark.parametrize("board", CYCLONE_V)
def test_cyclone_v_boards_generate_with_altera_pll(board: str) -> None:
    """The two Cyclone V boards use the altera_pll primitive."""
    result = generated(board)
    pll = next(t for n, t in result.files.items() if n.endswith("_pll.v"))
    check_in("altera_pll #(", pll)


@pytest.mark.parametrize("board", ALTPLL_BOARDS)
def test_the_other_four_boards_generate_with_altpll(board: str) -> None:
    """The four altpll boards generate a whole project."""
    result = generated(board)
    pll = next(t for n, t in result.files.items() if n.endswith("_pll.v"))
    check_in("altpll #(", pll)
    qsf = next(t for n, t in result.files.items() if n.endswith(".qsf"))
    check_in("set_location_assignment", qsf)
    sdc = next(t for n, t in result.files.items() if n.endswith(".sdc"))
    check_in("derive_pll_clocks", sdc)
    check_in("altpll_component", pll)


def test_the_de2_115_uses_a_burst_of_one_and_its_flash_chip() -> None:
    """Two x16 chips make a 32-bit bus; the NOR has its own package."""
    result = generated("de2-115")
    check_in('"0000000110000"', result.files["chip_is42s16320b_7_pkg.vhd"])
    check_in("chip_s29gl064n90_pkg.vhd", result.files)


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
