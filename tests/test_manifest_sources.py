"""Tests for the `manifest` rule and for `riscv-tools sources`."""

import argparse
from pathlib import Path

import pytest
from support import check_equal, check_false, check_in

from riscv_tools.cli.sources_cmd import cmd_sources
from riscv_tools.sources import SourcesError, ordered_sources
from riscv_tools.tree_check import check_tree

LOWER = """repository: Lower
provides:
  base:
    sources: [src/base.vhd]
"""
UPPER = """repository: Upper
provides:
  leaf:
    sources: [src/leaf.vhd, src/leaf_pkg.vhd]
    requires: [Lower/base]
  top:
    sources: [src/top.vhd]
    requires: [leaf, Lower/base]
"""


def _write(root: Path, name: str, text: str = "") -> None:
    """Create a file and the folders above it."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _manifest(root: Path) -> list[str]:
    """Run only the manifest rule."""
    return check_tree(root, "memory", ["manifest"])


def test_without_provides_the_rule_is_silent(tmp_path: Path) -> None:
    """A repository that declares nothing has nothing to check."""
    _write(tmp_path, "src/a.vhd")
    check_false(_manifest(tmp_path))


def test_a_complete_manifest_passes(tmp_path: Path) -> None:
    """Every file is listed once and every file exists."""
    _write(
        tmp_path,
        "paths.yaml",
        "repository: Here\nprovides:\n"
        "  leaf:\n    sources: [src/leaf.vhd, src/leaf_pkg.vhd]\n"
        "  top:\n    sources: [src/top.vhd]\n"
        "    requires: [leaf, Here/leaf]\n",
    )
    for name in ("leaf", "leaf_pkg", "top"):
        _write(tmp_path, f"src/{name}.vhd")
    check_equal(_manifest(tmp_path), [])


def test_unlisted_missing_duplicate_and_unknown(tmp_path: Path) -> None:
    """Each kind of mismatch is reported."""
    _write(
        tmp_path,
        "paths.yaml",
        "repository: R\nprovides:\n"
        "  a:\n    sources: [src/a.vhd, src/gone.vhd]\n"
        "    requires: [b, R/zzz]\n"
        "  b:\n    sources: [src/a.vhd]\n    requires: [a]\n",
    )
    _write(tmp_path, "src/a.vhd")
    _write(tmp_path, "src/orphan.vhd")
    problems = _manifest(tmp_path)
    for expected in (
        "manifest a: src/gone.vhd does not exist",
        "manifest src/a.vhd is listed by a and by b",
        "manifest src/orphan.vhd is listed by no component",
        "manifest a: requires R/zzz, which is not a component here",
        "manifest a: is part of a requires cycle",
    ):
        check_in(expected, problems)


def test_a_malformed_manifest_is_reported(tmp_path: Path) -> None:
    """A component without sources is a problem."""
    _write(tmp_path, "paths.yaml", "provides:\n  a:\n    requires: []\n")
    check_in(
        "manifest a: `sources` is a non-empty list of paths",
        _manifest(tmp_path),
    )


def test_the_repository_name_defaults_to_the_folder(tmp_path: Path) -> None:
    """Without `repository`, the root folder names the repository."""
    root = tmp_path / "Mine"
    _write(root, "paths.yaml", "provides:\n  a:\n    sources: [src/a.vhd]\n")
    _write(root, "src/a.vhd")
    check_equal(ordered_sources(root, ["Mine/a"]), ["src/a.vhd"])


def test_sources_orders_dependencies_first(tmp_path: Path) -> None:
    """Dependencies of another repository come before the target."""
    _write(tmp_path, "paths.yaml", UPPER)
    _write(tmp_path, ".gitmodules", "")
    _write(tmp_path, "src/common/paths.yaml", LOWER)
    check_equal(
        ordered_sources(tmp_path, ["top"]),
        [
            "src/common/src/base.vhd",
            "src/leaf.vhd",
            "src/leaf_pkg.vhd",
            "src/top.vhd",
        ],
    )


def test_sources_rejects_unknown_targets(tmp_path: Path) -> None:
    """A component or repository that is not declared fails."""
    _write(tmp_path, "paths.yaml", LOWER)
    with pytest.raises(SourcesError, match="Lower/nope not declared"):
        ordered_sources(tmp_path, ["nope"])
    with pytest.raises(SourcesError, match="Other not found"):
        ordered_sources(tmp_path, ["Other/x"])
    with pytest.raises(SourcesError, match="no provides"):
        ordered_sources(tmp_path / "empty", ["x"])


def test_the_subcommand_prints_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command prints one path per line, and exits 2 on error."""
    _write(tmp_path, "paths.yaml", LOWER)
    args = argparse.Namespace(root=str(tmp_path), target=["base"])
    cmd_sources(args)
    check_equal(capsys.readouterr().out, "src/base.vhd\n")
    args = argparse.Namespace(root=str(tmp_path), target=["nope"])
    with pytest.raises(SystemExit) as caught:
        cmd_sources(args)
    check_equal(caught.value.code, 2)
