"""Tests for the config keys that the platform map fixes."""

from pathlib import Path

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_in,
    check_not_in,
    dump_platform,
)
from test_config_pkg import MATRIX as CONFIG_PKG_MATRIX
from test_config_pkg import PLATFORM as CONFIG_PKG_PLATFORM

from riscv_tools.config_files import read_config
from riscv_tools.memory_map import config_from_platform, set_override

PLATFORM = {
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "profile": "rv32im_zicntr",
    "profiles": "matrix.yaml",
    "config": {
        "rom": "FLASH",
        "ram": "RAM",
        "addr_widths": ["boot_memory", "rom", "ram"],
    },
}


MATRIX = {
    "bases": [
        {"name": "rv32i", "generics": {"num_regs": 32}},
        {"name": "rv32e", "generics": {"num_regs": 16}},
    ],
    "extensions": [
        {"name": "Zicsr", "generic": "has_zicsr"},
        {"name": "Zicntr", "generic": "has_zicntr", "implies": ["has_zicsr"]},
        {"name": "M", "generic": "has_m", "base_letter": "m"},
    ],
    "mutually_exclusive": [["Zicsr", "Zicntr"]],
}


@pytest.fixture(autouse=True)
def _no_override():
    """Start each test with the profile of the platform."""
    set_override(None)
    yield
    set_override(None)


def _platform(root: Path) -> Path:
    (root / "matrix.yaml").write_text(yaml.safe_dump(MATRIX))
    path = root / "platform.yaml"
    path.write_text(dump_platform(PLATFORM))
    return path


def test_memory_and_widths_come_from_the_map(tmp_path: Path) -> None:
    """The words, bases, HTIF words and widths are derived."""
    config = config_from_platform(_platform(tmp_path))
    check_equal(
        config["memory"],
        {
            "boot_memory_base": 0,
            "boot_memory_words": 512,
            "rom_base": 0x800,
            "rom_words": 7680,
            "ram_base": 0x8000,
            "ram_words": 40960,
            "tohost_addr": 0x2FFE8,
            "fromhost_addr": 0x2FFF0,
        },
    )
    check_equal(config["isa"], {"base": "i"})
    check_equal(
        config["sim"]["env"],
        {
            "TOHOST_ADDR": "0x0002FFE8",
            "STDOUT_ADDR": "0x0002FBE0",
        },
    )
    check_equal(
        config["sim"]["parameters"],
        {
            "boot_memory_addr_width": "9",
            "rom_addr_width": "13",
            "ram_addr_width": "16",
        },
    )
    check_not_in("config_pkg", config["sim"])


def test_the_map_wins_over_what_the_config_says(tmp_path: Path) -> None:
    """A `memory_map` key replaces the values the files would give."""
    _platform(tmp_path)
    (tmp_path / "base.yaml").write_text(
        yaml.safe_dump({"memory": {"ram_words": 1, "other": 7}})
    )
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "extends": "base.yaml",
                "memory_map": "platform.yaml",
                "memory": {"ram_words": 2},
            }
        )
    )
    merged = read_config(tmp_path / "config.yaml")
    check_equal(merged["memory"]["ram_words"], 40960)
    check_equal(merged["memory"]["other"], 7)
    check_not_in("memory_map", merged)


def test_the_override_replaces_the_profile_of_the_platform(
    tmp_path: Path,
) -> None:
    """`--profile` picks the base, the registers and the extensions."""
    path = _platform(tmp_path)
    set_override("rv32e")
    config = config_from_platform(path)
    check_equal(config["isa"], {"base": "e"})
    for generic in ("HAS_E", "HAS_M"):
        check_not_in(generic, config["sim"]["parameters"])


def test_a_name_outside_the_specification_is_rejected(
    tmp_path: Path,
) -> None:
    """A profile that the specification does not list fails."""
    path = _platform(tmp_path)
    set_override("rv32im_zicsr_zicntr")
    with pytest.raises(ValueError, match="is not a profile"):
        config_from_platform(path)


LETTER_MATRIX = {
    "base": "rv32",
    "extensions": [
        {"name": "I", "base_letter": "i"},
        {"name": "E", "generic": "has_e", "base_letter": "e"},
        {"name": "Zicsr", "generic": "has_zicsr"},
        {"name": "Zicntr", "generic": "has_zicntr", "implies": ["has_zicsr"]},
        {"name": "M", "generic": "has_m", "base_letter": "m"},
    ],
    "mutually_exclusive": [["I", "E"], ["Zicsr", "Zicntr"]],
    "requires_any": [["I", "E"]],
}


def _letter_platform(root: Path) -> Path:
    (root / "matrix.yaml").write_text(yaml.safe_dump(LETTER_MATRIX))
    path = root / "platform.yaml"
    path.write_text(dump_platform(PLATFORM))
    return path


def test_the_letter_format_picks_the_base(tmp_path: Path) -> None:
    """The base letter follows the letter of the name."""
    path = _letter_platform(tmp_path)
    for name, base in (
        ("rv32im_zicntr", "i"),
        ("rv32em", "e"),
        ("rv32e", "e"),
    ):
        set_override(name)
        config = config_from_platform(path)
        check_equal(config["isa"], {"base": base})
        check_not_in("HAS_E", config["sim"]["parameters"])


def test_the_profile_reaches_the_core_through_the_config_pkg(
    tmp_path: Path,
) -> None:
    """The base and the extensions are constants of `sim.config_pkg`."""
    (tmp_path / "matrix.yaml").write_text(yaml.safe_dump(CONFIG_PKG_MATRIX))
    path = tmp_path / "platform.yaml"
    platform = {**CONFIG_PKG_PLATFORM, "config": PLATFORM["config"]}
    path.write_text(dump_platform(platform))
    for name, base_e in (
        ("rv32im_zicntr", "false"),
        ("rv32em_zicntr", "true"),
    ):
        set_override(name)
        text = config_from_platform(path)["sim"]["config_pkg"]
        check_in(f"constant IS_E : boolean := {base_e};", text)
        check_in("constant HAS_M             : boolean := true;", text)


def test_the_letter_format_rejects_a_name_with_no_letter(
    tmp_path: Path,
) -> None:
    """`rv32` with no I and no E is not a profile."""
    path = _letter_platform(tmp_path)
    for name in ("rv32", "rv32m", "rv32iem"):
        set_override(name)
        with pytest.raises(
            ValueError, match=r"rv32i or rv32e|is not a profile"
        ):
            config_from_platform(path)


def test_the_flash_banks_of_the_map_reach_the_config(tmp_path: Path) -> None:
    """The banks come out evaluated, for the tests that pack."""
    banks = [
        {"name": "A", "base": 0x1000, "size": "124K"},
        {"name": "B", "base": 0x20000, "size": "128K"},
    ]
    platform = {**PLATFORM, "flash": {"region": "FLASH", "banks": banks}}
    (tmp_path / "matrix.yaml").write_text(yaml.safe_dump(MATRIX))
    path = tmp_path / "platform.yaml"
    path.write_text(dump_platform(platform))
    config = config_from_platform(path)
    check_equal(
        config["flash"]["banks"],
        [
            {"name": "A", "base": 0x1000, "size": 124 * 1024},
            {"name": "B", "base": 0x20000, "size": 128 * 1024},
        ],
    )


def test_a_map_without_banks_adds_no_flash_key(tmp_path: Path) -> None:
    """A platform with a single image has no `flash` in its config."""
    check_not_in("flash", config_from_platform(_platform(tmp_path)))
