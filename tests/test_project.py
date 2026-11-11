"""Tests for the project commands and the files new-project writes."""

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from support import check, check_equal, check_false, check_in, check_not_in

from riscv_tools import cli
from riscv_tools.project import (
    Check,
    Manifest,
    board_idcode,
    build_command,
    check_cable,
    check_files,
    check_quartus,
    config_of_tests,
    find_manifest,
    flash_command,
    passed,
    read_manifest,
    render,
    render_tests_help,
    write_launcher,
    write_manifest,
)
from riscv_tools.project.tests_help import header_sed, header_values

MANIFEST = Manifest("demo-64k", "demo-board", "Insper-RISC-V", "src/f/demo")
PLATFORM: dict[str, Any] = {
    "regions": [
        {"name": "RAM", "base": 0x40000000, "size": "64K", "kind": "ram"},
    ],
    "reserved": {
        "stdout": {"base": 0x4000FBE0},
        "tohost": {"base": 0x4000FFE8},
    },
    "flash": {
        "banks": [
            {"name": "A", "base": 0x1000, "size": "32K"},
            {"name": "B", "base": 0x9000, "size": "32K"},
        ]
    },
}


def _project(root: Path) -> Path:
    """Write a project folder with its manifest and platform files."""
    write_manifest(root, MANIFEST)
    folder = root / "Insper-RISC-V/src/f/demo"
    folder.mkdir(parents=True)
    (folder / "config.yaml").write_text("quartus: {}\n")
    (folder / "platform.yaml").write_text(
        "platform: demo-64k\nregions:\n"
        "  - {name: RAM, base: 0x40000000, size: 64K, kind: ram}\n"
        "reserved:\n"
        "  stdout: {base: 0x4000FBE0}\n"
        "  tohost: {base: 0x4000FFE8}\n"
    )
    return root


def test_the_manifest_is_written_and_read_back(tmp_path: Path) -> None:
    """The four fields survive a round trip through the file."""
    path = write_manifest(tmp_path, MANIFEST)
    check_equal(path.name, "project.yaml")
    check_equal(read_manifest(path), MANIFEST)


def test_the_manifest_is_found_from_a_folder_inside(tmp_path: Path) -> None:
    """The search goes up from a subfolder to the project."""
    write_manifest(tmp_path, MANIFEST)
    inner = tmp_path / "Insper-RISC-V/src"
    inner.mkdir(parents=True)
    folder, manifest = find_manifest(inner)
    check_equal(folder, tmp_path)
    check_equal(manifest.name, "demo-64k")


def test_a_missing_or_incomplete_manifest_is_an_error(tmp_path: Path) -> None:
    """No file, or a file without a field, says what to do."""
    with pytest.raises(FileNotFoundError, match="new-project"):
        find_manifest(tmp_path)
    (tmp_path / "project.yaml").write_text("name: x\n")
    with pytest.raises(ValueError, match="board"):
        read_manifest(tmp_path / "project.yaml")


def test_the_launcher_mounts_the_quartus_and_shares_the_network(
    tmp_path: Path,
) -> None:
    """The script is executable, valid shell and lends host tools."""
    path = write_launcher(tmp_path)
    text = path.read_text()
    check(os.access(path, os.X_OK))
    check_in("--network host", text)
    check_in('-v "$QUARTUS_ROOT":"$QUARTUS_ROOT":ro', text)
    check_in("/opt/altera_lite", text)
    check_in("25.1std/quartus/bin", text)
    done = subprocess.run(["sh", "-n", str(path)], check=False)
    check_equal(done.returncode, 0)


def test_build_stops_after_the_chosen_quartus_step(tmp_path: Path) -> None:
    """The command is `program --stop-after` on the platform config."""
    command = build_command(tmp_path, MANIFEST, "map")
    check_equal(command[-3:], ["program", "--stop-after", "map"])
    check_in("src/f/demo/config.yaml", command)
    check_equal(command[command.index("--board") + 1], "demo-board")
    with pytest.raises(ValueError, match="stop-after"):
        build_command(tmp_path, MANIFEST, "synth")


def test_flash_holds_the_lock_of_the_board(tmp_path: Path) -> None:
    """The program runs inside `board lock --wait` on the same board."""
    config = config_of_tests(tmp_path, MANIFEST)
    config.parent.mkdir(parents=True)
    config.write_text("paths: {}\n")
    image = tmp_path / "p.mif"
    command = flash_command(tmp_path, MANIFEST, image)
    split = command.index("--")
    outer, inner = command[:split], command[split + 1 :]
    check_equal(outer[-4:], ["lock", "--board", "demo-board", "--wait"])
    check_equal(inner[-2:], ["program", str(image.resolve())])
    check_equal(inner[inner.index("--config") + 1], str(config))
    check_equal(inner[inner.index("--root") + 1], str(tmp_path / "Tests"))


def test_flash_needs_the_tests_to_be_prepared(tmp_path: Path) -> None:
    """Without the Tests config, flash says how to prepare it."""
    with pytest.raises(FileNotFoundError, match="project help"):
        flash_command(tmp_path, MANIFEST, tmp_path / "p.mif")


def test_the_files_of_the_platform_are_checked(tmp_path: Path) -> None:
    """Both files found pass; a missing one fails with advice."""
    _project(tmp_path)
    check(all(c.ok for c in check_files(tmp_path, MANIFEST)))
    (tmp_path / "Insper-RISC-V/src/f/demo/config.yaml").unlink()
    failed = [c for c in check_files(tmp_path, MANIFEST) if not c.ok]
    check_equal(len(failed), 1)
    check_in("create the project again", failed[0].detail)


def test_the_quartus_tools_are_looked_up_on_the_path() -> None:
    """A tool the lookup does not find fails with how to get it."""
    found = {"quartus_sh": "/q/quartus_sh", "jtagconfig": "/q/jtagconfig"}
    results = {c.name: c for c in check_quartus(found.get)}
    check(results["quartus_sh"].ok)
    check_false(results["quartus_pgm"].ok)
    check_in("./rt", results["quartus_pgm"].detail)


def test_a_missing_cable_is_a_warning_not_a_failure() -> None:
    """The cable is optional; a build needs no board."""
    seen = check_cable(lambda: "1) USB-Blaster [3-5]\n  02B050DD 5CE")
    check(seen.ok)
    check_equal(seen.detail, "1) USB-Blaster [3-5]")
    absent = check_cable(lambda: "No JTAG hardware available")
    check_false(absent.ok)
    check_in("warning", render([absent]))
    check(passed([absent]))
    check_false(passed([Check("quartus_sh", False, "missing")]))


def test_the_header_constants_follow_the_platform() -> None:
    """RAM end, host words and banks become header values and a sed."""
    values = header_values(PLATFORM)
    check_equal(values["RV32_RAM_END"], "0x40010000")
    check_equal(values["RV32_TOHOST"], "0x4000FFE8")
    check_equal(values["RV32_BANK_B_BASE"], "0x00009000")
    text = header_sed(values, "x/rv32_platform.h")
    check_in("sed -i -E", text)
    check_in("\\1" + "0x40010000", text)
    check_in("x/rv32_platform.h", text)


def test_the_tests_help_names_the_project_and_the_program() -> None:
    """The help uses the project's names and both languages exist."""
    pt = render_tests_help("pt", MANIFEST, PLATFORM)
    check_in("config.platform-demo-64k.yaml", pt)
    check_in("--only meu-programa", pt)
    check_in("0x4000FFE8", pt)
    en = render_tests_help("en", MANIFEST, PLATFORM)
    check_in("my-program", en)
    check_not_in("meu-programa", en)


def test_the_project_command_runs_build_in_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`project build` runs `program --stop-after sta` in the repo."""
    _project(tmp_path)
    seen: dict[str, Any] = {}

    def fake(command: list[str], **kw: Any) -> Any:
        seen["command"], seen["cwd"] = command, kw["cwd"]
        return subprocess.CompletedProcess[str](command, 0)

    monkeypatch.setattr("riscv_tools.cli.project_cmd.subprocess.run", fake)
    monkeypatch.setattr(
        "sys.argv", ["riscv-tools", "project", "build", "--dir", str(tmp_path)]
    )
    cli.main()
    check_equal(seen["cwd"], tmp_path / "Insper-RISC-V")
    check_equal(seen["command"][-2:], ["--stop-after", "sta"])


def test_flash_without_an_image_exits_with_status_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`project flash` needs the .mif of a program."""
    _project(tmp_path)
    argv = ["riscv-tools", "project", "flash", "--dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as stop:
        cli.main()
    check_equal(stop.value.code, 1)
    check_in(".mif", capsys.readouterr().err)


def test_the_project_command_needs_a_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Outside a project the command says how to create one."""
    argv = ["riscv-tools", "project", "doctor", "--dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as stop:
        cli.main()
    check_equal(stop.value.code, 1)
    check_in("new-project", capsys.readouterr().err)


def test_the_project_command_prints_the_tests_help(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`project help` prints the how-to with the platform's values."""
    _project(tmp_path)
    argv = ["riscv-tools", "project", "help", "--dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    out = capsys.readouterr().out
    check_in("Rodar os testes", out)
    check_in("0x40010000", out)


JTAG = (
    "1) USB-Blaster [1-2]\n  02B050DD   5CE(BA4|FA4)\n\n"
    "2) USB-Blaster [1-3]\n  020F70DD   10CL120(Y|Z)/EP3C120/..\n"
)


def test_the_cable_is_found_by_the_idcode_of_the_board() -> None:
    """With several boards, the cable listing the FPGA's IDCODE wins."""
    seen = check_cable(lambda: JTAG, idcode="020F70DD")
    check(seen.ok)
    check_in("USB-Blaster [1-3]", seen.detail)
    absent = check_cable(lambda: JTAG, idcode="031050DD")
    check_false(absent.ok)
    check_in("031050DD", absent.detail)


def test_the_idcode_comes_from_the_board_catalog(tmp_path: Path) -> None:
    """The chain entry marked `fpga` gives the IDCODE, in upper case."""
    folder = tmp_path / "boards/demo-board"
    folder.mkdir(parents=True)
    (folder / "board.yaml").write_text(
        "jtag:\n  chain:\n"
        "    - {name: hps, idcode: '4BA00477'}\n"
        "    - {name: fpga, idcode: '02b050dd', fpga: true}\n"
    )
    check_equal(board_idcode(tmp_path, "demo-board"), "02B050DD")
    check(board_idcode(tmp_path, "other") is None)


def test_the_launcher_takes_the_same_lock_as_the_host(tmp_path: Path) -> None:
    """The lock dir and the host name reach the container, exported."""
    text = write_launcher(tmp_path).read_text()
    check_in("-v /tmp:/tmp", text)
    check_in("export QUARTUS_ROOT RISCV_TOOLS_HOST", text)
    check_in("hostname -s", text)
