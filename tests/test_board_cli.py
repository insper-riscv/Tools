"""The `board` subcommands end to end, over fixtures."""

import json
import sys
from pathlib import Path

import pytest
from board_support import FIXTURES
from support import check_equal

from riscv_tools.board import runtime
from riscv_tools.cli.common import jtag_link
from riscv_tools.cli.parser import main
from riscv_tools.jtag.hardware import parse_jtagconfig


def _fake_port(bus: str) -> str:
    """Give a port path to a cable without the USB bus."""
    return f"port:{bus}"


def _fake_which(_name: str) -> str:
    """Pretend every tool is installed."""
    return "/bin/true"


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    jtagconfig: str,
    *argv: str,
) -> int:
    """Run `riscv-tools board ...` on a fixture host; give status."""
    text = (FIXTURES / "jtagconfig" / f"{jtagconfig}.txt").read_text()
    monkeypatch.setattr(runtime, "read_cables", lambda: parse_jtagconfig(text))
    monkeypatch.setattr(runtime, "port_path", _fake_port)
    monkeypatch.setenv("RISCV_TOOLS_HOST", "ws")
    prefix = ["riscv-tools", "--root", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", prefix + list(argv))
    try:
        main()
    except SystemExit as stop:
        return int(stop.code or 0)
    return 0


def _common(tmp_path: Path) -> list[str]:
    """Options that point the command at the fixtures."""
    return [
        "--boards-dir",
        str(FIXTURES / "boards"),
        "--inventory",
        str(tmp_path / "boards.yaml"),
        "--host",
        "ws",
    ]


def test_select_prints_json_for_a_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`select --board de0-cv --json` gives the cable and the lock."""
    code = _run(
        monkeypatch,
        tmp_path,
        "four-cables",
        "board",
        "select",
        *_common(tmp_path),
        "--board",
        "de0-cv",
        "--json",
    )
    data = json.loads(capsys.readouterr().out)
    check_equal(code, 0, "status")
    check_equal(data["cable"], "USB-Blaster [1-2]", "cable")
    check_equal(data["lock_file"], "/tmp/de0cv-ws.lock", "legacy lock file")  # noqa: S108


def test_select_fails_with_the_case_on_an_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two equal boards and no choice: status 2 and `case 2`."""
    code = _run(
        monkeypatch,
        tmp_path,
        "two-same",
        "board",
        "select",
        *_common(tmp_path),
        "--board",
        "de0-cv",
    )
    check_equal(code, 2, "status")
    check_equal("case 2" in capsys.readouterr().err, True, "case")


def test_select_all_lists_every_present_board(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--all` is how a runner splits the work over equal boards."""
    _run(
        monkeypatch,
        tmp_path,
        "two-same",
        "board",
        "select",
        *_common(tmp_path),
        "--board",
        "de0-cv",
        "--all",
    )
    found = json.loads(capsys.readouterr().out)
    check_equal(
        [s["cable"] for s in found],
        ["USB-Blaster [1-2]", "USB-Blaster [1-4]"],
        "cables",
    )


def test_an_idcode_without_a_package_selects_an_adhoc_board(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--idcode` serves a board that has no board.yaml yet."""
    code = _run(
        monkeypatch,
        tmp_path,
        "four-cables",
        "board",
        "select",
        "--inventory",
        str(tmp_path / "none.yaml"),
        "--host",
        "ws",
        "--boards-dir",
        str(tmp_path / "empty"),
        "--idcode",
        "02B050DD",
        "--json",
    )
    check_equal(code, 0, "status")
    check_equal(
        json.loads(capsys.readouterr().out)["cable"],
        "USB-Blaster [1-2]",
        "cable",
    )


def test_scan_save_writes_the_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`scan --save` records the four certain cables."""
    code = _run(
        monkeypatch,
        tmp_path,
        "four-cables",
        "board",
        "scan",
        *_common(tmp_path),
        "--save",
    )
    out = capsys.readouterr().out
    check_equal(code, 0, "status")
    saved = (tmp_path / "boards.yaml").read_text()
    check_equal("de0-cv-ws" in saved and "port:1-2" in saved, True, "entry")
    check_equal("inventory saved" in out, True, "message")


def test_lock_runs_the_command_under_the_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The command sees the board in its environment."""
    out = tmp_path / "env.txt"
    script = (
        "import os,sys;"
        "open(sys.argv[1],'w').write(os.environ['RISCV_TOOLS_CABLE']);"
        "sys.exit(7)"
    )
    code = _run(
        monkeypatch,
        tmp_path,
        "four-cables",
        "board",
        "lock",
        *_common(tmp_path),
        "--board",
        "de2-115",
        "--",
        sys.executable,
        "-c",
        script,
        str(out),
    )
    check_equal(code, 7, "the status of the command")
    check_equal(
        out.read_text(), "USB-Blaster [1-3]", "cable in the environment"
    )


def test_doctor_exits_one_on_a_broken_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A broken chain is a failure of the doctor."""
    monkeypatch.setattr("shutil.which", _fake_which)
    monkeypatch.setattr("riscv_tools.cli.board_id_cmd.read_usb", list)
    monkeypatch.setattr("riscv_tools.cli.board_id_cmd.list_cable_users", list)
    code = _run(
        monkeypatch, tmp_path, "broken", "board", "doctor", *_common(tmp_path)
    )
    check_equal(code, 1, "status")
    check_equal("[fail]" in capsys.readouterr().out, True, "report")


def test_the_link_of_a_project_without_jtag_device_comes_from_the_board(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """quartus.board gives the link its cable and device, no IDCODE."""
    text = (FIXTURES / "jtagconfig" / "four-cables.txt").read_text()
    monkeypatch.setattr(runtime, "read_cables", lambda: parse_jtagconfig(text))
    monkeypatch.setattr(runtime, "port_path", _fake_port)
    monkeypatch.setenv("RISCV_TOOLS_BOARDS", str(FIXTURES / "boards"))
    monkeypatch.setenv("RISCV_TOOLS_HOST", "ws")
    monkeypatch.chdir(tmp_path)
    cfg = {
        "quartus": {
            "jtag_device": None,
            "board": "de2-115",
            "boards": None,
            "sdram_debug_instance": 1,
        }
    }
    link = jtag_link(cfg)
    check_equal(link.hardware_name, "USB-Blaster [1-3]", "cable")
    check_equal(
        link.device_name, "@1: 10CL120(Y|Z)/EP3C120/.. (0x020F70DD)", "device"
    )
    check_equal(link.sdram_instance, 1, "instance")
