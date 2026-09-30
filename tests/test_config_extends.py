"""Tests for `extends:` in a project config (settings.load_config)."""

from pathlib import Path

import pytest

from riscv_tools.settings import load_config


def test_extends_merges_over_the_base(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text(
        "sim:\n  toplevel: core_sim\n  vhdl_sources: [a.vhd, b.vhd]\n"
    )
    (tmp_path / "variant.yaml").write_text(
        "extends: base.yaml\nsim:\n  toplevel: core_fpga\n  image: mif\n"
    )

    cfg = load_config(tmp_path / "variant.yaml")

    assert cfg["sim"]["toplevel"] == "core_fpga"
    assert cfg["sim"]["image"] == "mif"
    assert cfg["sim"]["vhdl_sources"] == ["a.vhd", "b.vhd"]
    assert "extends" not in cfg


def test_extends_replaces_a_list_instead_of_appending(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text("sim:\n  vhdl_sources: [a.vhd, b.vhd]\n")
    (tmp_path / "variant.yaml").write_text(
        "extends: base.yaml\nsim:\n  vhdl_sources: [c.vhd]\n"
    )

    assert load_config(tmp_path / "variant.yaml")["sim"]["vhdl_sources"] == ["c.vhd"]


def test_extends_is_relative_to_the_file_that_names_it(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "base.yaml").write_text("sim:\n  toplevel: top\n")
    (tmp_path / "shared" / "mid.yaml").write_text(
        "extends: base.yaml\nsim:\n  ghdl_std: '93'\n"
    )
    (tmp_path / "leaf.yaml").write_text("extends: shared/mid.yaml\n")

    cfg = load_config(tmp_path / "leaf.yaml")

    assert cfg["sim"]["toplevel"] == "top"
    assert cfg["sim"]["ghdl_std"] == "93"


def test_extends_loop_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("extends: b.yaml\n")
    (tmp_path / "b.yaml").write_text("extends: a.yaml\n")

    with pytest.raises(ValueError, match="loop"):
        load_config(tmp_path / "a.yaml")


def test_config_without_extends_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "only.yaml").write_text("sim:\n  toplevel: top\n")

    cfg = load_config(tmp_path / "only.yaml")

    assert cfg["sim"]["toplevel"] == "top"
    assert cfg["sim"]["image"] == "hex"
