"""Tests of the SDRAM backend: one controller for FLASH and RAM."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from multifpga_support import BOARDS, CHIPS, platform_file
from support import check_equal, check_in, check_not_in

from riscv_tools.board_generate import GenerateRequest, generate

MIB = 1 << 20
CACHE = {"size_bits": 32768}


def _segment(kind: str, base: int, size: int, **extra: Any) -> dict[str, Any]:
    """Write a segment; only `onchip` is read through the core port."""
    return {
        "type": kind,
        "base": base,
        "size": size,
        "on_bus": kind != "onchip",
        **extra,
    }


def _top(
    tmp_path: Path,
    instructions: dict[str, Any],
    data: dict[str, Any],
    board: str = "de0-cv",
    drop: tuple[str, ...] = (),
) -> tuple[str, list[str]]:
    """Generate the top of a board with the given segments.

    Returns the top, with blanks squeezed, and the warnings.
    """
    platform = yaml.safe_load(platform_file(board).read_text("utf-8"))
    platform["memory"]["instructions"] = [instructions]
    platform["memory"]["data"] = [data]
    for key in drop:
        platform["peripherals"].pop(key, None)
    irq: dict[str, Any] = platform.get("interrupts") or {}
    if "sources" in irq and drop:
        sources: list[dict[str, Any]] = irq["sources"]
        irq["sources"] = [s for s in sources if s["name"] != "FLASH"]
    path = tmp_path / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False), "utf-8")
    result = generate(
        GenerateRequest(path, None, BOARDS, CHIPS, accept_inferred=True)
    )
    top = next(t for n, t in result.files.items() if n.endswith("_top.vhd"))
    return " ".join(top.split()), result.warnings


def _split(
    tmp_path: Path, flash_mib: int, ram_mib: int, **data: Any
) -> tuple[str, list[str]]:
    """Generate the DE0-CV with FLASH and RAM sharing the SDRAM."""
    flash = _segment(
        "sdram",
        0x1000,
        flash_mib * MIB - 0x1000,
        offset=0x1000,
        cache=CACHE,
    )
    ram = _segment(
        "sdram",
        0x40000000,
        ram_mib * MIB,
        offset=flash_mib * MIB,
        cache=CACHE,
        **data,
    )
    return _top(tmp_path, flash, ram, drop=("FLASH_CTRL",))


def _count(text: str, needle: str) -> int:
    """Count the occurrences of a text."""
    return text.count(needle)


def test_the_two_regions_share_one_controller(tmp_path: Path) -> None:
    """One `sdram_ctrl`, one set of pins, one arbiter, one debug."""
    top, warnings = _split(tmp_path, 32, 32)
    check_equal([w for w in warnings if "no entity" in w], [])
    check_equal(_count(top, "entity work.sdram_ctrl"), 1)
    check_equal(_count(top, "entity work.sdram_arbiter"), 1)
    check_equal(_count(top, "entity work.sdram_dbg_master"), 1)
    check_in("sdram_data_bridge : entity work.sdram_cpu_bridge", top)
    check_in("sdram_instruction_bridge : entity work.sdram_cpu_bridge", top)


def test_the_32_32_split_forces_the_bit_above_the_low_25(
    tmp_path: Path,
) -> None:
    """The FLASH keeps the low half of the chip, the RAM the high."""
    top, warnings = _split(tmp_path, 32, 32)
    check_in(
        "rd_addr_c <= rd_addr(31 downto SDRAM_BYTE_BITS) & "
        "std_logic_vector(to_unsigned(1, SDRAM_BYTE_BITS - 25)) & "
        "rd_addr(24 downto 0);",
        top,
    )
    check_in(
        "fl_addr_c <= fl_addr(31 downto SDRAM_BYTE_BITS) & "
        "std_logic_vector(to_unsigned(0, SDRAM_BYTE_BITS - 25)) & "
        "fl_addr(24 downto 0);",
        top,
    )
    check_in("i_addr => rd_addr_c", top)
    check_in("i_addr => ins_addr", top)
    check_equal([w for w in warnings if "adder" in w], [])


def test_the_48_16_split_changes_the_bits_not_the_hardware(
    tmp_path: Path,
) -> None:
    """The FLASH has 26 low bits and the RAM 24, with the constant 3."""
    top, _ = _split(tmp_path, 48, 16)
    check_in("fl_addr(25 downto 0);", top)
    check_in(
        "std_logic_vector(to_unsigned(3, SDRAM_BYTE_BITS - 24)) & "
        "rd_addr(23 downto 0);",
        top,
    )
    check_in("assert 3 < 2 ** (SDRAM_BYTE_BITS - 24)", top)


def test_the_16_48_split_adds_a_constant_to_the_ram_address(
    tmp_path: Path,
) -> None:
    """A RAM offset that is not a multiple of its window is a sum."""
    top, warnings = _split(tmp_path, 16, 48)
    check_in(
        "rd_addr_c <= rd_addr(31 downto SDRAM_BYTE_BITS) & "
        "std_logic_vector(resize(unsigned(rd_addr(25 downto 0)), "
        "SDRAM_BYTE_BITS) + to_unsigned(16777216, SDRAM_BYTE_BITS));",
        top,
    )
    check_in("fl_addr(23 downto 0);", top)
    check_equal([w for w in warnings if "adder" in w] != [], True)


def test_a_flash_in_the_sdram_has_no_flash_controller(tmp_path: Path) -> None:
    """No `flash_loader`, `flash_cmd_port`, `FLASH_CTRL` or storage."""
    top, _ = _split(tmp_path, 32, 32)
    for name in (
        "flash_loader",
        "flash_cmd_port",
        "flash_chip",
        "flash_jtag_shell",
        "fcmd_valid",
        "has_flash_ctrl",
        "FLASH_CTRL",
    ):
        check_not_in(name, top)


def test_the_debug_port_holds_the_core_while_the_flash_is_written(
    tmp_path: Path,
) -> None:
    """The level of `hold` reaches the core clock and its reset."""
    top, _ = _split(tmp_path, 32, 32)
    check_in("o_core_hold => core_hold", top)
    check_in("core_hold_sr <= core_hold_sr(0) & core_hold;", top)
    check_in("flash_halt <= core_hold_sr(1);", top)
    check_in("soc_rst <= rst_sr(1) or flash_halt;", top)


def test_the_reset_button_does_not_restart_the_controller(
    tmp_path: Path,
) -> None:
    """Only the lock of the PLL resets the controller of the SDRAM."""
    top, _ = _split(tmp_path, 32, 32)
    check_in("rst_mem_async <= not pll_locked;", top)
    check_not_in("rst_mem_async <= (not pll_locked) or reset_active", top)


def test_executing_from_the_ram_is_a_choice_of_the_platform(
    tmp_path: Path,
) -> None:
    """Without `fetch` the instruction port never reaches the RAM."""
    top, _ = _split(tmp_path, 32, 32)
    check_not_in("flash_arbiter", top)
    check_in("ri_ready <= '0';", top)
    with_fetch, _ = _split(tmp_path, 32, 32, fetch=True)
    check_in("sdram_instruction_mux : entity work.flash_arbiter", with_fetch)
    check_in("i_b_addr => ri_addr_c", with_fetch)
    check_in("o_a_ready => fl_ready", with_fetch)
    check_not_in("ri_ready <= '0';", with_fetch)


def test_the_flash_face_of_the_soc_reaches_the_bridge(tmp_path: Path) -> None:
    """The SoC wires the `fl_*` face, and the bridge answers it."""
    top, _ = _split(tmp_path, 32, 32)
    for formal in ("addr", "rden", "line", "advance", "ready", "rdata"):
        check_in(f"flash_{formal} => fl_", top)
    check_in("fl_ready <= ins_ready;", top)
    check_in("fl_busy <= fl_rden and not fl_ready;", top)


def test_a_instructions_in_the_chip_with_the_data_on_the_core_port(
    tmp_path: Path,
) -> None:
    """Option c, the data in the FPGA: only the instruction bridge."""
    flash = _segment("sdram", 0x1000, 8 * MIB - 0x1000, cache=CACHE)
    ram = _segment("emulated", 0x40000000, 64 * 1024, cache=CACHE)
    ram["latency"] = {"first": 2, "next": 1}
    top, _ = _top(tmp_path, flash, ram, drop=("FLASH_CTRL",))
    check_equal(_count(top, "entity work.sdram_ctrl"), 1)
    check_in("sdram_instruction_bridge", top)
    check_not_in("sdram_data_bridge", top)
    check_in("a_req <= '0';", top)
    check_in("ram_port_inst : entity work.onchip_ram_port", top)
    check_equal(_count(top, "ri_ready <= '0';"), 1)


def test_option_a_the_instructions_in_the_fpga_and_the_data_in_the_sdram(
    tmp_path: Path,
) -> None:
    """The instruction memory is on the core port: no FLASH face."""
    flash = _segment("onchip", 0x1000, 252 * 1024)
    ram = _segment("sdram", 0x40000000, 64 * MIB, cache=CACHE)
    top, _ = _top(tmp_path, flash, ram, drop=("FLASH_CTRL",))
    check_in("sdram_data_bridge", top)
    check_not_in("sdram_instruction_bridge", top)
    check_in("i_req <= '0';", top)
    check_not_in("core_hold", top)
    check_not_in("o_flash_addr", top)
    check_in("rom_external => false", top)


def test_option_b_the_instructions_emulated_and_the_data_in_the_sdram(
    tmp_path: Path,
) -> None:
    """The emulated FLASH keeps its storage and its loader."""
    flash = _segment(
        "emulated",
        0x1000,
        252 * 1024,
        latency={"first": 24, "next": 4},
        sector_bytes=4096,
        cache=CACHE,
    )
    ram = _segment("sdram", 0x40000000, 64 * MIB, cache=CACHE)
    top, _ = _top(tmp_path, flash, ram)
    check_in("flash_chip_inst : entity work.flash_chip", top)
    check_in("flash_loader_inst : entity work.flash_loader", top)
    check_equal(_count(top, "entity work.sdram_ctrl"), 1)
    check_not_in("sdram_instruction_bridge", top)
    check_in("rom_external => true", top)


def test_option_d_the_instructions_in_a_real_nor_chip(tmp_path: Path) -> None:
    """The NOR keeps its controller beside the SDRAM of the data."""
    flash = _segment("flash", 0x1000, 1024 * 1024, cache=CACHE)
    ram = _segment("sdram", 0x40000000, 128 * MIB, cache=CACHE)
    top, _ = _top(tmp_path, flash, ram, board="de2-115")
    check_in("nor_ctrl_inst : entity work.nor_flash_ctrl", top)
    check_equal(_count(top, "entity work.sdram_ctrl"), 1)
    check_in("sdram_data_bridge", top)
    check_not_in("sdram_instruction_bridge", top)
    check_not_in("core_hold", top)
    check_in("o_flash_addr => fx_addr", top)


def test_option_d_with_the_data_in_the_sram(tmp_path: Path) -> None:
    """The NOR and the SRAM, and no SDRAM controller at all."""
    flash = _segment("flash", 0x1000, 1024 * 1024, cache=CACHE)
    ram = _segment("sram", 0x40000000, 2 * MIB, cache=CACHE)
    top, _ = _top(tmp_path, flash, ram, board="de2-115")
    check_in("nor_ctrl_inst : entity work.nor_flash_ctrl", top)
    check_in("sram_ctrl_inst : entity work.sram_ctrl", top)
    check_not_in("sdram_ctrl", top)


@pytest.mark.parametrize("fetch", [False, True])
def test_a_platform_without_offset_keeps_the_address(
    tmp_path: Path, fetch: bool
) -> None:
    """The DE2-115 of today: the SoC address goes to the bridge."""
    flash = _segment("flash", 0x1000, 1024 * 1024, cache=CACHE)
    ram = _segment("sdram", 0x40000000, 128 * MIB, cache=CACHE, fetch=fetch)
    top, _ = _top(tmp_path, flash, ram, board="de2-115")
    check_in("rd_addr_c <= rd_addr;", top)
    check_equal("SDRAM_BYTE_BITS - " in top, False)
    check_equal("sdram_instruction_bridge" in top, fetch)
