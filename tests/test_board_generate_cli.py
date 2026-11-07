"""Tests for the `board generate` subcommand."""

import argparse
import shutil
from pathlib import Path

import pytest
from multifpga_support import FIXTURES
from support import check, check_equal, check_in

from riscv_tools import memory_map
from riscv_tools.cli.board_generate_cmd import cmd_board_generate
from riscv_tools.memory_map import Mismatch


@pytest.fixture(autouse=True)
def written(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Stand in for the memory map files."""
    platforms: list[Path] = []

    def write_all(platform: Path, root: Path) -> list[Path]:
        platforms.append(platform)
        return [root / "m.vhd"]

    monkeypatch.setattr(memory_map, "write_all", write_all)

    def check_all(_platform: Path, _root: Path) -> tuple[int, list[Mismatch]]:
        return 1, []

    monkeypatch.setattr(memory_map, "check_all", check_all)
    return platforms


def _root(tmp_path: Path) -> Path:
    """Copy the fixtures where the command looks for them."""
    shutil.copytree(FIXTURES / "boards", tmp_path / "boards")
    shutil.copytree(FIXTURES / "chips", tmp_path / "Memory" / "chips")
    shutil.copytree(FIXTURES / "platforms", tmp_path / "platforms")
    shutil.copytree(FIXTURES / "handwritten", tmp_path / "hand")
    return tmp_path


def _args(root: Path, **changes: object) -> argparse.Namespace:
    """Arguments of `board generate`."""
    base: dict[str, object] = {
        "root": str(root),
        "platform": "platforms/de0-cv.yaml",
        "select_board": None,
        "out": "build",
        "boards_dir": None,
        "chips_dir": None,
        "target": [],
        "seed": 5,
        "accept_inferred_pins": False,
        "check": False,
        "hand_qsf": None,
        "hand_sdc": None,
        "hand_pll": None,
        "ignore_source": [],
    }
    return argparse.Namespace(**(base | changes))


def test_the_command_writes_the_project_under_the_build_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The output is `build/<platform>-<board>/`."""
    root = _root(tmp_path)
    cmd_board_generate(_args(root))
    check((root / "build" / "de0-cv-de0-cv" / "de0_cv_de0_cv.qsf").is_file())
    check_in("project written to", capsys.readouterr().out)


def test_the_report_flags_exit_zero_when_nothing_is_lost(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Against the real files, only generated names differ."""
    root = _root(tmp_path)
    sources = ["--ignore-source"]
    del sources
    ignored = [
        line.rsplit("/", 1)[-1].split()[-1]
        for line in (root / "hand" / "de0-cv.qsf").read_text().splitlines()
        if line.startswith(
            (
                "set_global_assignment -name VHDL_FILE",
                "set_global_assignment -name QIP_FILE",
                "set_global_assignment -name VERILOG_FILE",
            )
        )
    ]
    cmd_board_generate(
        _args(
            root,
            hand_qsf=str(root / "hand" / "de0-cv.qsf"),
            hand_sdc=str(root / "hand" / "de0-cv.sdc"),
            hand_pll=str(root / "hand" / "sdram_platform_pll.v"),
            ignore_source=ignored,
        )
    )
    out = capsys.readouterr().out
    check_in("[pins] equivalent", out)
    check_in("[pll] equivalent", out)
    check_in("[sources] equivalent", out)


def test_an_invalid_input_exits_with_status_two(tmp_path: Path) -> None:
    """An unknown board is an input error, status 2."""
    root = _root(tmp_path)
    with pytest.raises(SystemExit) as caught:
        cmd_board_generate(_args(root, select_board="de2-116"))
    check_equal(caught.value.code, 2)


def test_check_passes_after_a_write_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--check` writes nothing and finds a file that differs."""
    root = _root(tmp_path)
    cmd_board_generate(_args(root))
    qsf = root / "build" / "de0-cv-de0-cv" / "de0_cv_de0_cv.qsf"
    cmd_board_generate(_args(root, check=True))
    qsf.write_text(qsf.read_text() + "# edited by hand\n")
    with pytest.raises(SystemExit) as caught:
        cmd_board_generate(_args(root, check=True))
    check_equal(caught.value.code, 1)
    check_in("out of date", capsys.readouterr().err)
    check_in("# edited by hand", qsf.read_text())


def test_check_reports_a_project_that_was_never_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing project is a problem of `--check`, not a write."""
    root = _root(tmp_path)
    with pytest.raises(SystemExit) as caught:
        cmd_board_generate(_args(root, check=True))
    check_equal(caught.value.code, 1)
    check_in("missing", capsys.readouterr().err)
    check(not (root / "build").exists())


def test_the_memory_map_goes_through_generate_memory_map(
    tmp_path: Path,
    written: list[Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A platform with `generate` gets its map from the same code."""
    root = _root(tmp_path)
    cmd_board_generate(_args(root))
    check_equal([path.name for path in written], ["de0-cv.yaml"])
    check_in("generated: m.vhd", capsys.readouterr().out)
    cmd_board_generate(_args(root, check=True))
    check_equal(len(written), 1)
