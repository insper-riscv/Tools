"""Tests for the config paths that the platform's `generate` names."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_not_in,
    dump_platform,
)
from test_config_from_platform import MATRIX

from riscv_tools.config_files import read_config
from riscv_tools.memory_map import set_override

GENERATE: dict[str, Any] = {
    "specs": {"path": "r/plain.specs", "rom": "FLASH", "ram": "RAM"},
    "bank_specs": [
        {"path": "r/bank-a.specs", "rom": "BANK_A_PAYLOAD", "ram": "RAM"},
        {"path": "r/bank-b.specs", "rom": "BANK_B_PAYLOAD", "ram": "RAM"},
    ],
    "boot_ld": {"path": "r/boot.ld"},
}


@pytest.fixture(autouse=True)
def _no_override():
    """Start each test with the profile of the platform."""
    set_override(None)
    yield
    set_override(None)


def _write(root: Path, generate: dict[str, Any] | None) -> None:
    """Write the platform, its matrix and nothing else."""
    (root / "matrix.yaml").write_text(yaml.safe_dump(MATRIX))
    platform: dict[str, Any] = {
        "regions": MAP_REGIONS,
        "reserved": MAP_RESERVED,
        "profile": "rv32im_zicntr",
        "profiles": "matrix.yaml",
        "config": {"rom": "FLASH", "ram": "RAM", "addr_widths": ["rom"]},
    }
    if generate is not None:
        platform["generate"] = generate
    (root / "platform.yaml").write_text(dump_platform(platform))


def _config(root: Path, body: dict[str, Any], name: str = "config.yaml"):
    """Write a config that names the platform and read it."""
    (root / name).write_text(
        yaml.safe_dump({"memory_map": "platform.yaml", **body})
    )
    return read_config(root / name)


def test_the_specs_and_the_linker_come_from_generate(tmp_path: Path) -> None:
    """A config that names neither takes the paths of the platform."""
    _write(tmp_path, GENERATE)
    merged = _config(tmp_path, {})
    check_equal(merged["toolchain"]["specs"], "r/plain.specs")
    check_equal(merged["paths"]["boot_memory_linker_script"], "r/boot.ld")


def test_a_flash_image_bank_picks_the_specs_of_that_bank(
    tmp_path: Path,
) -> None:
    """Programs packed for bank B link with the specs of bank B."""
    _write(tmp_path, GENERATE)
    merged = _config(tmp_path, {"flash_image": {"bank": "B"}})
    check_equal(merged["toolchain"]["specs"], "r/bank-b.specs")


def test_the_bank_may_come_from_the_base_config(tmp_path: Path) -> None:
    """A config that extends another keeps the bank of that one."""
    _write(tmp_path, GENERATE)
    (tmp_path / "base.yaml").write_text(
        yaml.safe_dump({"flash_image": {"bank": "A", "version": 1}})
    )
    merged = _config(tmp_path, {"extends": "base.yaml"})
    check_equal(merged["toolchain"]["specs"], "r/bank-a.specs")


def test_what_the_config_writes_wins_over_the_platform(
    tmp_path: Path,
) -> None:
    """The paths of `generate` are only defaults."""
    _write(tmp_path, GENERATE)
    merged = _config(
        tmp_path,
        {
            "toolchain": {"specs": "mine.specs"},
            "paths": {"boot_memory_linker_script": "mine.ld"},
        },
    )
    check_equal(merged["toolchain"]["specs"], "mine.specs")
    check_equal(merged["paths"]["boot_memory_linker_script"], "mine.ld")


def test_a_platform_without_generate_adds_no_paths(tmp_path: Path) -> None:
    """Nothing is invented when the platform writes no such file."""
    _write(tmp_path, None)
    merged = _config(tmp_path, {})
    check_not_in("specs", merged.get("toolchain", {}))
    check_not_in("boot_memory_linker_script", merged.get("paths", {}))
