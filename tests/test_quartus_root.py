"""Tests of the Quartus folder that the environment can move."""

import os
from pathlib import Path

import pytest
from support import check_equal, check_is

from riscv_tools.quartus_root import (
    DEFAULT_ROOT,
    DEFAULT_VERSION,
    ROOT_VAR,
    VERSION_VAR,
    bin_dir,
    core,
    prepend_to_path,
)


def _install(root: Path, version: str) -> Path:
    """Create the bin folder of one Quartus version."""
    folder = root / version / "quartus" / "bin"
    folder.mkdir(parents=True)
    return folder


def test_the_default_folder_is_the_opt_install() -> None:
    """Without variables the folder is the one of the install guide."""
    check_equal(
        bin_dir({}),
        Path(DEFAULT_ROOT) / DEFAULT_VERSION / "quartus" / "bin",
    )


def test_an_empty_variable_counts_as_unset() -> None:
    """A variable left empty by a script keeps the default."""
    check_equal(bin_dir({ROOT_VAR: "", VERSION_VAR: ""}), bin_dir({}))


def test_the_variables_move_the_root_and_the_version(tmp_path: Path) -> None:
    """Both variables take part in the folder."""
    env = {ROOT_VAR: str(tmp_path), VERSION_VAR: "26.1std"}
    check_equal(bin_dir(env), tmp_path / "26.1std" / "quartus" / "bin")


def test_a_chosen_root_goes_to_the_front_of_the_path(tmp_path: Path) -> None:
    """The person's folder wins over a Quartus already on the PATH."""
    folder = _install(tmp_path, DEFAULT_VERSION)
    env = {ROOT_VAR: str(tmp_path), "PATH": "/usr/bin"}
    check_is(prepend_to_path(env), True)
    check_equal(env["PATH"].split(os.pathsep), [str(folder), "/usr/bin"])


def test_the_default_root_goes_to_the_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the variable the folder only fills a gap."""
    folder = _install(tmp_path, DEFAULT_VERSION)
    monkeypatch.setattr(core, "DEFAULT_ROOT", str(tmp_path))
    env = {"PATH": "/usr/bin"}
    check_is(prepend_to_path(env), True)
    check_equal(env["PATH"].split(os.pathsep), ["/usr/bin", str(folder)])


def test_a_missing_folder_leaves_the_path_alone(tmp_path: Path) -> None:
    """Nothing is added when the Quartus is not there."""
    env = {ROOT_VAR: str(tmp_path / "none"), "PATH": "/usr/bin"}
    check_is(prepend_to_path(env), False)
    check_equal(env["PATH"], "/usr/bin")


def test_a_folder_already_on_the_path_is_not_repeated(tmp_path: Path) -> None:
    """Running twice does not grow the PATH."""
    _install(tmp_path, DEFAULT_VERSION)
    env = {ROOT_VAR: str(tmp_path), "PATH": "/usr/bin"}
    check_is(prepend_to_path(env), True)
    check_is(prepend_to_path(env), False)
    check_equal(env["PATH"].count(str(tmp_path)), 1)
