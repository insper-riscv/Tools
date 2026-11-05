"""Tests that the checks leave out the files of submodules."""

import json
from pathlib import Path

from support import check_equal

from riscv_tools.repo_walk import list_files, submodule_paths
from riscv_tools.sources import ordered_sources
from riscv_tools.tree_check import check_tree

GITMODULES = """[submodule "Common-Components"]
\tpath = src/common
\turl = https://github.com/insper-riscv/Common-Components.git
"""
MANIFEST = """repository: Here
provides:
  top:
    sources: [src/top.vhd]
    requires: [Common-Components/leaf]
"""
COMMON_MANIFEST = """repository: Common-Components
provides:
  leaf:
    sources: [src/leaf.vhd]
"""


def _write(root: Path, name: str, text: str = "") -> None:
    """Create a file and the folders above it."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repository(root: Path, marker: bool) -> None:
    """Build a repository with a simulated submodule at `src/common`."""
    _write(root, ".gitmodules", GITMODULES)
    _write(root, "paths.yaml", MANIFEST)
    _write(root, "src/top.vhd", "entity top is\nend entity;\n")
    _write(root, "src/common/paths.yaml", COMMON_MANIFEST)
    _write(root, "src/common/src/leaf.vhd", "entity leaf is\nend entity;\n")
    _write(root, "src/common/tests/vhdl/leaf_tb.vhd")
    if marker:
        _write(root, "src/common/.git", "gitdir: ../../.git/modules/x\n")
    _write(
        root,
        "tests/python/tests.json",
        json.dumps({"T": {"toplevel": "top", "sources": ["src/top.vhd"]}}),
    )


def test_paths_are_read_from_gitmodules(tmp_path: Path) -> None:
    """The submodule paths come from `.gitmodules`, without `.git`."""
    _write(tmp_path, ".gitmodules", GITMODULES)
    check_equal(sorted(submodule_paths(tmp_path)), ["src/common"])
    check_equal(sorted(submodule_paths(tmp_path / "missing")), [])


def test_a_broken_gitmodules_names_no_submodule(tmp_path: Path) -> None:
    """A `.gitmodules` that cannot be parsed excludes nothing."""
    _write(tmp_path, ".gitmodules", "path = src/common\n")
    check_equal(sorted(submodule_paths(tmp_path)), [])


def test_manifest_ignores_files_of_a_submodule(tmp_path: Path) -> None:
    """The files of `src/common` are not demanded of this manifest."""
    _repository(tmp_path, marker=True)
    check_equal(check_tree(tmp_path, "core", ["manifest"]), [])


def test_manifest_ignores_a_submodule_without_git(tmp_path: Path) -> None:
    """A copy with no `.git` (rsync) still leaves the submodule out."""
    _repository(tmp_path, marker=False)
    check_equal(check_tree(tmp_path, "core", ["manifest"]), [])


def test_coverage_and_location_ignore_a_submodule(tmp_path: Path) -> None:
    """Entity coverage and VHDL location skip the submodule's files."""
    _repository(tmp_path, marker=False)
    rules = ["entity-coverage", "vhdl-location"]
    check_equal(check_tree(tmp_path, "core", rules), [])


def test_the_walk_lists_own_files_only(tmp_path: Path) -> None:
    """The listing keeps own files and drops the submodule's."""
    _repository(tmp_path, marker=False)
    found = {
        path.relative_to(tmp_path).as_posix()
        for path in list_files(tmp_path, ".vhd", "src")
    }
    check_equal(found, {"src/top.vhd"})


def test_a_folder_that_is_not_a_submodule_is_still_checked(
    tmp_path: Path,
) -> None:
    """Only the paths of `.gitmodules` are left out."""
    _repository(tmp_path, marker=False)
    _write(tmp_path, "src/other/extra.vhd")
    problems = check_tree(tmp_path, "core", ["manifest"])
    check_equal(
        problems,
        ["manifest src/other/extra.vhd is listed by no component"],
    )


def test_sources_still_follow_requires_into_the_submodule(
    tmp_path: Path,
) -> None:
    """`sources` reads the submodule's manifest for `requires`."""
    _repository(tmp_path, marker=False)
    files = ordered_sources(tmp_path, ["top"])
    check_equal(files, ["src/common/src/leaf.vhd", "src/top.vhd"])
