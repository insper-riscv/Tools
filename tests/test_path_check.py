import argparse
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from riscv_tools import cli
from riscv_tools.path_check import check_paths, collect


def _tree(root: Path) -> None:
    """Lay out a parent with a nested Tests project and a shared src/."""
    (root / "src").mkdir()
    for name in ("a.vhd", "b.vhd"):
        (root / "src" / name).write_text("")
    (root / "Tests" / "tools").mkdir(parents=True)
    (root / "Tests" / "tools" / "config.yaml").write_text(
        yaml.safe_dump(
            {"sim": {"vhdl_sources": ["../src/a.vhd", "../src/b.vhd", "$ENV/x.vhd"]}}
        )
    )
    (root / "Tests" / "tests.json").write_text(
        json.dumps(
            {
                "one": {"sources": ["../src/a.vhd"]},
                "two": {"sources": ["../src/b.vhd"]},
            }
        )
    )
    (root / "q").mkdir()
    (root / "q" / "p.qsf").write_text(
        "set_global_assignment -name VHDL_FILE ../src/a.vhd\n"
        "set_global_assignment -name QIP_FILE ip/x.qip\n"
    )
    (root / "q" / "ip").mkdir()
    (root / "q" / "ip" / "x.qip").write_text("")


def _manifest(root: Path, references: list[dict[str, Any]]) -> Path:
    path = root / "paths.yaml"
    path.write_text(yaml.safe_dump({"references": references}))
    return path


YAML_REF = {
    "name": "sim",
    "file": "Tests/tools/config.yaml",
    "yaml": "sim.vhdl_sources",
    "base": "Tests",
}
JSON_REF = {
    "name": "json",
    "file": "Tests/tests.json",
    "yaml": "*.sources",
    "base": "Tests",
}
QSF_REF = {"name": "qsf", "file": "q/p.qsf", "pattern": r"_FILE (\S+)"}


def test_collect_reads_a_yaml_list_relative_to_base_and_skips_env_vars(
    tmp_path: Path,
) -> None:
    _tree(tmp_path)
    paths = collect(YAML_REF, tmp_path)
    assert paths == [
        tmp_path / "Tests" / "../src/a.vhd",
        tmp_path / "Tests" / "../src/b.vhd",
    ]


def test_collect_walks_a_wildcard_over_a_mapping(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert len(collect(JSON_REF, tmp_path)) == 2


def test_collect_defaults_base_to_the_files_directory(tmp_path: Path) -> None:
    _tree(tmp_path)
    paths = collect(QSF_REF, tmp_path)
    assert paths == [tmp_path / "q" / "../src/a.vhd", tmp_path / "q" / "ip/x.qip"]


def test_check_passes_when_every_path_exists(tmp_path: Path) -> None:
    _tree(tmp_path)
    manifest = _manifest(
        tmp_path, [YAML_REF, JSON_REF, QSF_REF, {"name": "dirs", "paths": ["src"]}]
    )
    assert check_paths(manifest, tmp_path) == (2 + 2 + 2 + 1, [])


def test_check_reports_a_path_that_was_moved(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / "src" / "b.vhd").rename(tmp_path / "src" / "moved.vhd")
    manifest = _manifest(tmp_path, [YAML_REF, JSON_REF])
    _, problems = check_paths(manifest, tmp_path)
    assert problems == [
        "sim: missing src/b.vhd",
        "json: missing src/b.vhd",
    ]


def test_check_fails_when_a_reference_yields_nothing(tmp_path: Path) -> None:
    _tree(tmp_path)
    renamed = {**YAML_REF, "yaml": "sim.sources"}
    _, problems = check_paths(_manifest(tmp_path, [renamed]), tmp_path)
    assert "no path found" in problems[0]


def test_check_allows_an_optional_reference_to_yield_nothing(tmp_path: Path) -> None:
    _tree(tmp_path)
    optional = {**YAML_REF, "yaml": "sim.sources", "optional": True}
    assert check_paths(_manifest(tmp_path, [optional]), tmp_path) == (0, [])


def test_check_reports_an_unreadable_file_and_a_bad_entry(tmp_path: Path) -> None:
    _tree(tmp_path)
    missing = {"name": "gone", "file": "nope.yaml", "yaml": "x"}
    bad = {"name": "bad", "file": "Tests/tests.json"}
    _, problems = check_paths(_manifest(tmp_path, [missing, bad]), tmp_path)
    assert problems[0].startswith("gone:")
    assert "needs `paths`, `yaml` or `pattern`" in problems[1]


def test_cmd_check_paths_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path)
    _manifest(tmp_path, [YAML_REF])
    args = argparse.Namespace(root=str(tmp_path), manifest="paths.yaml")
    cli.cmd_check_paths(args)
    assert "paths OK: 2 paths" in capsys.readouterr().out

    (tmp_path / "src" / "a.vhd").unlink()
    with pytest.raises(SystemExit) as exc:
        cli.cmd_check_paths(args)
    assert exc.value.code == 1
    assert "PATH sim: missing src/a.vhd" in capsys.readouterr().err
