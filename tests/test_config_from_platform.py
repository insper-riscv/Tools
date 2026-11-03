"""Tests for the config keys that the platform map fixes."""

from pathlib import Path

import yaml

from riscv_tools.memory_map import config_from_platform
from riscv_tools.settings import read_config

PLATFORM = {
    "regions": [
        {"name": "BOOT_ROM", "base": "0x0", "size": "2K", "exec": True},
        {"name": "FLASH", "base": "0x800", "size": "30K", "exec": True},
        {"name": "RAM", "base": "0x8000", "size": "160K", "kind": "ram"},
    ],
    "reserved": {
        "stdout": {"base": "0x2FBE0", "size": "1K+8"},
        "tohost": {"base": "0x2FFE8", "size": "8"},
        "fromhost": {"base": "0x2FFF0", "size": "8"},
    },
    "config": {
        "rom": "FLASH",
        "ram": "RAM",
        "addr_widths": ["boot_rom", "rom", "ram"],
    },
}


def _platform(root: Path) -> Path:
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(PLATFORM, sort_keys=False))
    return path


def test_memory_and_widths_come_from_the_map(tmp_path: Path) -> None:
    """The words, bases, HTIF words and widths are derived."""
    config = config_from_platform(_platform(tmp_path))
    assert config["memory"] == {
        "boot_rom_base": 0,
        "boot_rom_words": 512,
        "rom_base": 0x800,
        "rom_words": 7680,
        "ram_base": 0x8000,
        "ram_words": 40960,
        "tohost_addr": 0x2FFE8,
        "fromhost_addr": 0x2FFF0,
    }
    assert config["sim"]["env"] == {
        "TOHOST_ADDR": "0x0002FFE8",
        "STDOUT_ADDR": "0x0002FBE0",
    }
    assert config["sim"]["parameters"] == {
        "boot_rom_addr_width": "9",
        "rom_addr_width": "13",
        "ram_addr_width": "16",
    }


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
    assert merged["memory"]["ram_words"] == 40960
    assert merged["memory"]["other"] == 7
    assert "memory_map" not in merged
