"""Tests that the version of the package is stated once, in the toml."""

import tomllib
from pathlib import Path

import riscv_tools

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_version_matches_pyproject() -> None:
    """`riscv_tools.__version__` is the `version` of `pyproject.toml`.

    The release tag is `v` and this version, so the two numbers must not
    drift apart.
    """
    project = tomllib.loads(PYPROJECT.read_text())["project"]
    assert riscv_tools.__version__ == project["version"]
