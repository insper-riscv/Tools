"""Tests for the `config_pkg` that a simulation compiles per profile."""

from pathlib import Path

import pytest
from support import check_equal

from riscv_tools.sim_runner import with_profile_config_pkg


def test_an_empty_text_keeps_the_sources(tmp_path: Path) -> None:
    """Without `sim.config_pkg` the sources are compiled as they are."""
    sources = ["a/config_pkg.vhd", "b/top.vhd"]
    check_equal(with_profile_config_pkg(sources, "", tmp_path), sources)
    check_equal(list(tmp_path.iterdir()), [])


def test_the_profile_copy_takes_the_place_of_the_file(tmp_path: Path) -> None:
    """The file is swapped in the same position, the rest is kept."""
    sources = ["a/utils.vhd", "b/config_pkg.vhd", "b/top.vhd"]
    swapped = with_profile_config_pkg(sources, "package text", tmp_path / "x")
    copy = tmp_path / "x" / "config_pkg.vhd"
    check_equal(swapped, ["a/utils.vhd", str(copy), "b/top.vhd"])
    check_equal(copy.read_text(encoding="utf-8"), "package text")


def test_a_text_with_no_file_to_replace_is_refused(tmp_path: Path) -> None:
    """A `sim.config_pkg` that no source can take is a config error."""
    with pytest.raises(ValueError, match=r"no source is config_pkg\.vhd"):
        with_profile_config_pkg(["b/top.vhd"], "package text", tmp_path)
