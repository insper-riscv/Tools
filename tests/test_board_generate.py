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
        "if_addr(log2_exact(BOOT_MEMORY_SIZE_BYTES) - 3 downto 0)",
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
        "display_vjtag : entity work.virtual_jtag",
        "instance_index => 2",
        "i_display_tck => display_tck",
        "o_display_fail => display_fail",
        "LEDR <= (0 => display_fail, others => '0');",
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


def test_the_de0_cv_top_keeps_the_timing_cuts_and_the_update_path() -> None:
    """The board top asks the soc for the cuts of the hand top."""
    top = " ".join(_top("de0-cv").split())
    for fragment in (
        "registered_irqs => true",
        "has_access_faults => HAS_ACCESS_FAULTS",
        "periph_slots => PERIPH_SLOTS",
        "fast_icache_select => true",
        "has_dcache_bypass => true, bypass_page => RAM_LAST_PAGE",
        "has_flash_ctrl => true, flash_ctrl_id => 3",
        "o_flash_cmd_valid => fcmd_valid",
        "i_inval_valid => fcmd_inval_valid",
        "flash_cmd_inst : entity work.flash_cmd_port",
        "sector_bytes => 4096",
        "i_address_b => st_address_b",
        "st_wren_b <= ld_wren_b when flash_halt = '1' else fcmd_b_we;",
    ):
        check_in(fragment, top)


def test_a_flash_without_the_update_controller_has_no_command_chip() -> None:
    """Only a platform with FLASH_CTRL gets the command chip."""
    top = " ".join(_top("de10-nano").split())
    check_not_in("flash_cmd_port", top)
    check_not_in("has_flash_ctrl", top)
    check_in("i_address_b => ld_address_b", top)


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


def test_the_de2_115_gets_the_nor_and_the_32_bit_sdram_backends() -> None:
    """The NOR controller and the 32-bit SDRAM are instantiated."""
    result = generated("de2-115")
    check_equal([w for w in result.warnings if "clk_phase_ps" not in w], [])
    top = " ".join(_top("de2-115").split())
    check_in("nor_ctrl_inst : entity work.nor_flash_ctrl", top)
    check_in("sdram_ctrl_inst : entity work.sdram_ctrl", top)
    check_in("constant SDRAM_DQ : natural := 32;", top)
    check_in("dq_width => SDRAM_DQ", top)
    check_in("generic map (addr_bits => SDRAM_ADDR_BITS)", top)
    check_in("DRAM_DQM <= dqm;", top)
    check_in("signal dqm : std_logic_vector(4 - 1 downto 0);", top)


def test_the_nor_backend_subtracts_the_start_of_the_flash_region() -> None:
    """The SoC speaks in absolute addresses and the chip in offsets."""
    top = " ".join(_top("de2-115").split())
    check_in("nor_rd_addr <= std_logic_vector(unsigned(fx_addr) - ", top)
    check_in("nor_cmd_addr <= std_logic_vector(unsigned(fcmd_addr) - ", top)
    check_in(
        "base_addr => std_logic_vector(to_unsigned(ROM_BASE_KIB * 1024", top
    )
    check_in("o_flash_addr => fx_addr", top)
    check_not_in("o_flash_addr => fl_addr", top)


def test_the_nor_pins_are_free_of_timing_requirements() -> None:
    """The controller counts the cycles of the chip: false paths."""
    sdc = next(
        t for n, t in generated("de2-115").files.items() if n.endswith(".sdc")
    )
    check_in("set_false_path -from [get_ports {FL_DQ[*]}]", sdc)
    check_in("set_false_path -from [get_ports {FL_RY}]", sdc)
    check_in("set_false_path -to   [get_ports {FL_ADDR[*]}]", sdc)


def test_the_chip_package_of_the_nor_has_its_size() -> None:
    """The NOR package carries the size the controller takes."""
    pkg = generated("de2-115").files["chip_s29gl064n90_pkg.vhd"]
    check_in("constant SIZE_BYTES : natural := 8388608;", pkg)


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


def test_only_the_cyclone_v_projects_keep_the_slew_rate() -> None:
    """Only the Cyclone V families keep `SLEW_RATE`."""
    for name, slew in (
        ("de10-lite", False),
        ("de0-cv", True),
        ("de2-115", False),
    ):
        files = generated(name).files
        qsf = next(t for n, t in files.items() if n.endswith(".qsf"))
        check_in("CURRENT_STRENGTH_NEW DEFAULT", qsf)
        check_equal("SLEW_RATE 1" in qsf, slew)
