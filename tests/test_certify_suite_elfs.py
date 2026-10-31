"""certify: the tests that run from the RAM variant of the target."""

from pathlib import Path
from typing import Any

import pytest

from riscv_tools.certify import core


def _target(vendor: Path, name: str, tests: list[str]) -> Path:
    """Write a test_config.yaml named `name` and a fake ELF per test."""
    config = vendor / f"{name}.yaml"
    config.write_text(f"name: {name}\n")
    elfs = vendor / "work" / name / "elfs"
    elfs.mkdir(parents=True)
    for test in tests:
        (elfs / f"{test}.elf").write_bytes(b"")
    return config


def _cfg(**act: Any) -> dict[str, Any]:
    """Build a config with the keys that suite_elfs reads."""
    base = {
        "vendor_dir": ".",
        "target_config": "flash.yaml",
        "extensions": "I,Zifencei",
        "jobs": 1,
    }
    return {"act": {**base, **act}}


def test_without_ram_tests_the_target_alone_runs(tmp_path: Path) -> None:
    """Without ram_tests the run takes every ELF of the target."""
    _target(tmp_path, "flash", ["a", "fence"])
    elfs = core.suite_elfs(_cfg(), tmp_path, build=False)
    assert [e.stem for e in elfs] == ["a", "fence"]


def test_a_ram_test_comes_from_the_variant(tmp_path: Path) -> None:
    """A test of ram_tests is taken from the variant, once."""
    _target(tmp_path, "flash", ["a", "fence"])
    _target(tmp_path, "flash-ram", ["a", "fence"])
    cfg = _cfg(ram_tests=["fence"], ram_target_config="flash-ram.yaml")
    elfs = core.suite_elfs(cfg, tmp_path, build=False)
    assert [e.stem for e in elfs] == ["a", "fence"]
    assert elfs[0].parent.parent.name == "flash"
    assert elfs[1].parent.parent.name == "flash-ram"


def test_a_missing_variant_elf_is_reported(tmp_path: Path) -> None:
    """A test of ram_tests without an ELF in the variant raises."""
    _target(tmp_path, "flash", ["a", "fence"])
    _target(tmp_path, "flash-ram", ["a"])
    cfg = _cfg(ram_tests=["fence"], ram_target_config="flash-ram.yaml")
    with pytest.raises(FileNotFoundError):
        core.suite_elfs(cfg, tmp_path, build=False)
