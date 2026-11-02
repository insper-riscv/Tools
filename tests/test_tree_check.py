"""Tests for tree_check."""

import argparse
from pathlib import Path

import pytest

from riscv_tools import cli
from riscv_tools.cli.tree_cmd import cmd_check_tree
from riscv_tools.tree_check import (
    FORMAL_FILES,
    KINDS,
    STANDARD_FILES,
    VHDL_FILES,
    check_tree,
    rule_names,
)

GITMODULES = """[submodule "Common-Components"]
\tpath = src/common
\turl = https://github.com/insper-riscv/Common-Components.git
"""


def _write(path: Path, text: str = "") -> None:
    """Create a file and the folders above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _conforming(root: Path) -> None:
    """Lay out a Core repository that meets every rule."""
    folders = {".github/workflows", "src", "tests/python/unittests"}
    for name in (*STANDARD_FILES, *VHDL_FILES, *FORMAL_FILES):
        if name in folders:
            (root / name).mkdir(parents=True, exist_ok=True)
        else:
            _write(root / name)
    for name in (
        "src/core/core.vhd",
        "src/I/alu.vhd",
        "tests/vhdl/alu_tb.vhd",
        "docs/pt-br/pipeline/README.md",
        "docs/en/pipeline/README.md",
    ):
        _write(root / name)
    _write(root / ".gitmodules", GITMODULES)
    _write(root / "paths.yaml", "tree:\n  identifier_folders: [I]\n")


def test_a_conforming_tree_has_no_problem(tmp_path: Path) -> None:
    """A repository that meets every rule passes."""
    _conforming(tmp_path)
    assert not check_tree(tmp_path, "core")


def test_standard_files_reports_each_missing_file(tmp_path: Path) -> None:
    """A missing standard file is reported by name."""
    _conforming(tmp_path)
    (tmp_path / "CITATION.cff").unlink()
    (tmp_path / "formal" / "run.sh").unlink()
    problems = check_tree(tmp_path, "core", ["standard-files"])
    assert problems == [
        "standard-files missing CITATION.cff",
        "standard-files missing formal/run.sh",
    ]


def test_common_components_needs_no_formal_folder(tmp_path: Path) -> None:
    """The kind without proofs is not asked for `formal/run.sh`."""
    _conforming(tmp_path)
    (tmp_path / "formal" / "run.sh").unlink()
    assert not check_tree(tmp_path, "common-components")


def test_language_pairs_reports_a_missing_half(tmp_path: Path) -> None:
    """A README without its English half is reported."""
    _conforming(tmp_path)
    (tmp_path / "README.en.md").unlink()
    problems = check_tree(tmp_path, "core", ["language-pairs"])
    assert problems == [
        "language-pairs missing README.en.md, the pair of its other half"
    ]


def test_language_pairs_reports_a_document_without_its_mirror(
    tmp_path: Path,
) -> None:
    """A document has the same path in the other language."""
    _conforming(tmp_path)
    _write(tmp_path / "docs" / "pt-br" / "ISA" / "I" / "alu.md")
    _write(tmp_path / "docs" / "en" / "pipeline" / "extra.md")
    problems = check_tree(tmp_path, "core", ["language-pairs"])
    assert problems == [
        "language-pairs missing docs/en/ISA/I/alu.md, mirror of pt-br",
        "language-pairs missing docs/pt-br/pipeline/extra.md, mirror of en",
    ]


def test_vhdl_location_reports_a_file_outside_src(tmp_path: Path) -> None:
    """A `.vhd` outside `src/` and `tests/vhdl/` fails."""
    _conforming(tmp_path)
    _write(tmp_path / "common" / "adder.vhd")
    _write(tmp_path / "top.vhd")
    problems = check_tree(tmp_path, "core", ["vhdl-location"])
    assert problems == [
        "vhdl-location top.vhd is outside src/ and tests/vhdl/",
        "vhdl-location common/adder.vhd is outside src/ and tests/vhdl/",
    ]


def test_vhdl_location_leaves_out_build_output_and_submodules(
    tmp_path: Path,
) -> None:
    """Build output and submodule folders are not checked."""
    _conforming(tmp_path)
    _write(tmp_path / "build" / "work" / "gen.vhd")
    _write(tmp_path / "other" / "x.vhd")
    _write(tmp_path / "other" / ".git")
    assert not check_tree(tmp_path, "core", ["vhdl-location"])


def test_common_submodule_requires_the_mount_at_src_common(
    tmp_path: Path,
) -> None:
    """Common-Components must be declared at `src/common`."""
    _conforming(tmp_path)
    (tmp_path / ".gitmodules").write_text(
        GITMODULES.replace("src/common", "Common-Components")
    )
    problems = check_tree(tmp_path, "core", ["common-submodule"])
    assert problems == [
        "common-submodule src/common is not declared in .gitmodules"
    ]


def test_common_submodule_requires_the_right_repository(
    tmp_path: Path,
) -> None:
    """The submodule at `src/common` must be Common-Components."""
    _conforming(tmp_path)
    (tmp_path / ".gitmodules").write_text(
        GITMODULES.replace("Common-Components.git", "Memory.git")
    )
    problems = check_tree(tmp_path, "core", ["common-submodule"])
    assert len(problems) == 1
    assert "not Common-Components" in problems[0]


def test_common_submodule_is_reported_without_gitmodules(
    tmp_path: Path,
) -> None:
    """A repository with no `.gitmodules` does not mount it."""
    _conforming(tmp_path)
    (tmp_path / ".gitmodules").unlink()
    assert check_tree(tmp_path, "core", ["common-submodule"]) == [
        "common-submodule src/common is not declared in .gitmodules"
    ]


def test_folder_names_reject_space_accent_and_capitals(
    tmp_path: Path,
) -> None:
    """A folder a build tool would split or mangle is reported."""
    _conforming(tmp_path)
    (tmp_path / "docs" / "pt-br" / "meu doc").mkdir()
    (tmp_path / "docs" / "pt-br" / "memória").mkdir()
    (tmp_path / "src" / "Cache").mkdir()
    problems = check_tree(tmp_path, "core", ["folder-names"])
    assert [line.split(":")[0] for line in problems] == [
        "folder-names docs/pt-br/memória",
        "folder-names docs/pt-br/meu doc",
        "folder-names src/Cache",
    ]


def test_folder_names_accept_the_identifiers_listed_in_paths_yaml(
    tmp_path: Path,
) -> None:
    """Identifiers named in `paths.yaml` keep their capitals."""
    _conforming(tmp_path)
    (tmp_path / "src" / "Zicsr").mkdir()
    assert check_tree(tmp_path, "core", ["folder-names"]) == [
        "folder-names src/Zicsr: use lowercase letters, digits and hyphens,"
        " with no space or accent"
    ]
    (tmp_path / "paths.yaml").write_text(
        "tree:\n  identifier_folders: [I, Zicsr]\n"
    )
    assert not check_tree(tmp_path, "core", ["folder-names"])


def test_folder_names_leave_out_vendor_code(tmp_path: Path) -> None:
    """Third-party code keeps the names it came with."""
    _conforming(tmp_path)
    (tmp_path / "src" / "vendor" / "OpenCores_Uart").mkdir(parents=True)
    assert not check_tree(tmp_path, "core", ["folder-names"])


def test_rules_depend_on_the_kind() -> None:
    """The layout rules of VHDL do not apply to the other kinds."""
    assert rule_names("tools") == ["standard-files", "language-pairs"]
    assert rule_names("core") == [
        "standard-files",
        "language-pairs",
        "vhdl-location",
        "common-submodule",
        "folder-names",
    ]
    assert "common-submodule" not in rule_names("common-components")
    assert set(KINDS) >= {"top", "tests", "certification", "infra"}


def test_an_unknown_kind_or_rule_is_an_error(tmp_path: Path) -> None:
    """A kind or rule that does not exist or apply fails."""
    with pytest.raises(ValueError, match="unknown kind"):
        check_tree(tmp_path, "nothing")
    with pytest.raises(ValueError, match="does not apply to tools"):
        check_tree(tmp_path, "tools", ["vhdl-location"])


def test_cmd_check_tree_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command prints OK, or exits 1 listing the problems."""
    _conforming(tmp_path)
    args = argparse.Namespace(
        kind="core", only=None, root=str(tmp_path), config=None
    )
    cmd_check_tree(args)
    assert "tree OK: core" in capsys.readouterr().out
    (tmp_path / "LICENSE").unlink()
    with pytest.raises(SystemExit) as failed:
        cmd_check_tree(args)
    assert failed.value.code == 1
    assert "TREE standard-files missing LICENSE" in capsys.readouterr().err
    bad = argparse.Namespace(
        kind="core", only="nothing", root=str(tmp_path), config=None
    )
    with pytest.raises(SystemExit) as unknown:
        cmd_check_tree(bad)
    assert unknown.value.code == 2


def test_the_subcommand_is_registered_without_a_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`riscv-tools check-tree` runs without `--config`."""
    _conforming(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "riscv-tools",
            "--root",
            str(tmp_path),
            "check-tree",
            "--kind",
            "core",
            "--only",
            "standard-files,language-pairs",
        ],
    )
    cli.main()
    assert "rules standard-files, language-pairs" in capsys.readouterr().out
