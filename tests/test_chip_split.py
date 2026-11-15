"""Tests of `offset`, the split of one chip and `on_bus`."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_schema import SchemaError, parse_platform_fields
from riscv_tools.memory_map import chip_split, load_platform
from riscv_tools.memory_map.platform_h import render_platform_h
from riscv_tools.memory_map.problems import platform_problems
from riscv_tools.sdram_windows import (
    WindowError,
    window_named,
    windows_from_config,
    windows_from_platform,
)

MIB = 1 << 20
FLASH_BASE = 0x1000
RAM_BASE = 0x40000000


def _segment(kind: str, base: int, size: int, **extra: Any) -> dict[str, Any]:
    """Write one segment on the bus."""
    on_bus = kind != "onchip"
    return {
        "type": kind,
        "base": base,
        "size": size,
        "on_bus": on_bus,
        **extra,
    }


def split(flash_mib: int, ram_mib: int, **extra: Any) -> dict[str, Any]:
    """Write a memory block that splits one chip in two."""
    flash = flash_mib * MIB - FLASH_BASE
    return {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [
            _segment("sdram", FLASH_BASE, flash, offset=FLASH_BASE)
        ],
        "data": [
            _segment(
                "sdram",
                RAM_BASE,
                ram_mib * MIB,
                offset=flash_mib * MIB,
                **extra,
            )
        ],
    }


def load(root: Path, memory: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Write a platform with the memory block and load it."""
    data = {"memory": memory, **changes}
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return load_platform(path)


@pytest.mark.parametrize(
    ("sizes", "bits", "ram_high", "aligned"),
    [
        ((32, 32), (25, 25), 1, True),
        ((48, 16), (26, 24), 3, True),
        ((16, 48), (24, 26), 0, False),
    ],
)
def test_the_split_is_what_the_platform_writes(
    tmp_path: Path,
    sizes: tuple[int, int],
    bits: tuple[int, int],
    ram_high: int,
    aligned: bool,
) -> None:
    """The 32/32, 48/16 and 16/48 MiB splits, with nothing fixed."""
    flash, ram = sizes
    flash_bits, ram_bits = bits
    platform = load(tmp_path, split(flash, ram))
    check_equal(chip_split.problems(platform), [])
    found = chip_split.windows(platform)
    check_equal(found["FLASH"].low_bits, flash_bits)
    check_equal(found["FLASH"].offset, FLASH_BASE)
    check_equal(found["FLASH"].aligned, True)
    check_equal(found["FLASH"].fixed_high, 0)
    check_equal(found["RAM"].low_bits, ram_bits)
    check_equal(found["RAM"].offset, flash * MIB)
    check_equal(found["RAM"].aligned, aligned)
    check_equal(found["RAM"].fixed_high, ram_high if aligned else 0)
    check_equal(found["RAM"].end, (flash + ram) * MIB)


def test_the_window_table_of_the_host_follows_the_split(
    tmp_path: Path,
) -> None:
    """The word of the chip of an address is offset plus distance."""
    table = windows_from_platform(load(tmp_path, split(16, 48)))
    ram = window_named(table, "ram")
    check_equal(ram.word_address(RAM_BASE), 16 * MIB // 4)
    check_equal(ram.word_address(RAM_BASE + 8), 16 * MIB // 4 + 2)
    flash = window_named(table, "FLASH")
    check_equal(flash.word_address(FLASH_BASE), FLASH_BASE // 4)
    with pytest.raises(WindowError, match="outside"):
        flash.word_address(RAM_BASE)
    with pytest.raises(WindowError, match="word aligned"):
        flash.word_address(FLASH_BASE + 2)


def test_a_region_without_offset_keeps_the_address_of_the_soc(
    tmp_path: Path,
) -> None:
    """Only the RAM in the SDRAM: no window, the chip identity."""
    memory = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("emulated", FLASH_BASE, 252 * 1024)],
        "data": [_segment("sdram", RAM_BASE, 64 * MIB)],
    }
    platform = load(tmp_path, memory)
    check_equal(chip_split.windows(platform), {})
    check_equal(windows_from_platform(platform)["RAM"].offset, 0)
    check_not_in(
        "CHIP_OFFSET", render_platform_h(platform, _table(), "p.yaml")
    )


def _table() -> dict[str, int]:
    """Give the symbols that the header of the platform reads."""
    return {"RAM.base": RAM_BASE, "RAM.end": RAM_BASE + 1, "FLASH.size": 1}


def test_the_header_of_the_platform_carries_the_split(
    tmp_path: Path,
) -> None:
    """The host and the programs read the window from the header."""
    platform = load(tmp_path, split(32, 32))
    table = _table() | {"FLASH.size": 32 * MIB - FLASH_BASE}
    text = render_platform_h(platform, table, "p.yaml")
    check_in("#define RV32_FLASH_CHIP_OFFSET 0x00001000", text)
    check_in("#define RV32_RAM_CHIP_OFFSET 0x02000000", text)
    check_in("#define RV32_RAM_CHIP_LOW_BITS 0x00000019", text)
    check_in("#define RV32_RAM_CHIP_HIGH 0x00000001", text)
    check_in("#define RV32_FLASH_WINDOW_KIB 0x00007FFC", text)


def test_the_window_table_of_the_config_repeats_the_platform() -> None:
    """`memory.sdram_windows` and the legacy RAM of the config."""
    cfg = {
        "memory": {
            "sdram_windows": {
                "FLASH": {"base": 0x1000, "size": "31M", "offset": 0x1000},
                "RAM": {"base": 0x40000000, "size": "32M", "offset": "32M"},
            }
        }
    }
    table = windows_from_config(cfg)
    check_equal(table["RAM"].offset, 32 * MIB)
    check_equal(table["FLASH"].size, 31 * MIB)
    legacy = windows_from_config(
        {"memory": {"ram_base": RAM_BASE, "ram_words": 1024}}
    )
    check_equal(legacy["RAM"].size, 4096)
    check_equal(windows_from_config({}), {})
    with pytest.raises(WindowError, match="not in the sdram"):
        window_named(legacy, "FLASH")


def test_two_regions_in_one_chip_must_not_overlap(tmp_path: Path) -> None:
    """The ranges of the chip are checked, not the SoC addresses."""
    memory = split(32, 32)
    memory["data"][0]["offset"] = 16 * MIB
    found = chip_split.problems(load(tmp_path, memory))
    check_in("overlaps", str(found[0]))


def test_two_regions_in_one_chip_both_need_an_offset(tmp_path: Path) -> None:
    """A split is explicit: one offset alone is refused."""
    memory = split(32, 32)
    del memory["data"][0]["offset"]
    found = chip_split.problems(load(tmp_path, memory))
    check_in("share the sdram chip", str(found[0]))


@pytest.mark.parametrize(
    ("kind", "offset", "message"),
    [
        ("emulated", 0x1000, "only valid with type sdram"),
        ("sdram", 0x1001, "multiples of 4096"),
        ("sdram", -4096, "multiples of 4096"),
    ],
)
def test_an_offset_is_checked(
    tmp_path: Path, kind: str, offset: int, message: str
) -> None:
    """Only the SDRAM has it, and it is a whole number of pages."""
    memory = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("emulated", FLASH_BASE, 252 * 1024)],
        "data": [_segment(kind, RAM_BASE, 64 * MIB, offset=offset)],
    }
    found = chip_split.problems(load(tmp_path, memory))
    check_in(message, " ".join(str(f) for f in found))


def test_the_flash_controller_needs_a_flash_the_core_can_program(
    tmp_path: Path,
) -> None:
    """A FLASH in the SDRAM has no FLASH_CTRL and no PLIC line 6."""
    peripherals = {"FLASH_CTRL": {"base": 0xB0000000, "size": 16}}
    platform = load(tmp_path, split(32, 32), peripherals=peripherals)
    found = [str(p) for p in platform_problems(platform)]
    check(any("FLASH_CTRL needs a FLASH" in line for line in found))
    clean = load(tmp_path, split(32, 32))
    check(
        not any("FLASH_CTRL" in str(p) for p in platform_problems(clean)),
        "without FLASH_CTRL the platform is accepted",
    )


@pytest.mark.parametrize("kind", ["onchip", "emulated", "sdram", "sram"])
def test_the_data_memory_takes_every_type_but_flash(
    tmp_path: Path, kind: str
) -> None:
    """`onchip`, `emulated`, `sdram` and `sram` are data memories."""
    memory = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("onchip", FLASH_BASE, 4096)],
        "data": [_segment(kind, RAM_BASE, 4096)],
    }
    platform = load(tmp_path, memory)
    check_equal(platform["regions"][2]["base"], RAM_BASE)


def test_the_data_memory_refuses_flash(tmp_path: Path) -> None:
    """The CPU does not write a flash by an ordinary access."""
    memory = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("onchip", FLASH_BASE, 4096)],
        "data": [_segment("flash", RAM_BASE, 4096)],
    }
    with pytest.raises(ValueError, match=r"memory\.data\.type flash is not"):
        load(tmp_path, memory)


@pytest.mark.parametrize(
    "kind", ["onchip", "emulated", "flash", "sram", "sdram"]
)
def test_the_instruction_memory_takes_the_five_types(
    tmp_path: Path, kind: str
) -> None:
    """`instructions` is every memory the core can fetch from."""
    memory = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment(kind, FLASH_BASE, 4096)],
        "data": [_segment("onchip", RAM_BASE, 4096)],
    }
    check_in("regions", load(tmp_path, memory))


def test_on_bus_false_is_the_port_of_the_core(tmp_path: Path) -> None:
    """Outside the core the memory is read through the bus."""
    memory: dict[str, Any] = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("sdram", FLASH_BASE, 4096)],
        "data": [_segment("sdram", RAM_BASE, 4096)],
    }
    memory["instructions"][0]["on_bus"] = False
    with pytest.raises(ValueError, match="needs on_bus: true"):
        load(tmp_path, memory)
    onchip = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("onchip", FLASH_BASE, 4096)],
        "data": [_segment("onchip", RAM_BASE, 4096)],
    }
    platform = load(tmp_path, onchip)
    check_equal(platform["memory"]["rom"], {"external": False})
    check_equal(platform["memory"]["ram"], {"external": False})


def test_on_bus_true_over_onchip_is_refused_by_the_board_fields(
    tmp_path: Path,
) -> None:
    """A board platform has to name the device behind the bus."""
    memory: dict[str, Any] = {
        "boot": {"base": 0, "size": "4K"},
        "instructions": [_segment("onchip", FLASH_BASE, 4096)],
        "data": [_segment("onchip", RAM_BASE, 4096)],
    }
    memory["data"][0]["on_bus"] = True
    platform = load(
        tmp_path,
        memory,
        clocks={"core": {"mhz": 50}},
        board="auto",
        boards=["de0-cv"],
        platform="x",
    )
    with pytest.raises(SchemaError, match="backend is required"):
        parse_platform_fields(platform)


def test_fetch_belongs_to_the_data_in_the_sdram(tmp_path: Path) -> None:
    """The instruction port reaches the RAM if the platform says so."""
    memory = split(32, 32, fetch=True)
    platform = load(tmp_path, memory)
    check_equal(platform["memory"]["ram"]["fetch"], True)
    wrong = split(32, 32)
    wrong["instructions"][0]["fetch"] = True
    with pytest.raises(ValueError, match="only belongs to the data"):
        load(tmp_path, wrong)
