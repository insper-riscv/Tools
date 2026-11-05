"""Tests for the config keys that the platform map fixes."""

from pathlib import Path

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_is,
    check_not_in,
)

from riscv_tools.memory_map import config_from_platform, set_override
from riscv_tools.settings import read_config

PLATFORM = {
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "profile": "rv32im_zicntr",
    "profiles": "matrix.yaml",
    "config": {
        "rom": "FLASH",
        "ram": "RAM",
        "addr_widths": ["boot_rom", "rom", "ram"],
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
    path.write_text(yaml.safe_dump(PLATFORM, sort_keys=False))
    return path


def test_memory_and_widths_come_from_the_map(tmp_path: Path) -> None:
    """The words, bases, HTIF words and widths are derived."""
    config = config_from_platform(_platform(tmp_path))
    check_equal(
        config["memory"],
        {
            "boot_rom_base": 0,
            "boot_rom_words": 512,
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
            "boot_rom_addr_width": "9",
            "rom_addr_width": "13",
            "ram_addr_width": "16",
            "HAS_E": False,
            "HAS_ZICSR": True,
            "HAS_ZICNTR": True,
            "HAS_M": True,
        },
    )


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
    check_is(config["sim"]["parameters"]["HAS_E"], True)
    check_is(config["sim"]["parameters"]["HAS_M"], False)


def test_a_name_outside_the_specification_is_rejected(
    tmp_path: Path,
) -> None:
    """A profile that the specification does not list fails."""
    path = _platform(tmp_path)
    set_override("rv32im_zicsr_zicntr")
    with pytest.raises(ValueError, match="is not a profile"):
        config_from_platform(path)
