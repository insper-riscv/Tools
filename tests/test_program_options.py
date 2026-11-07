"""Tests for the compile options of `program` and its compile script.

The old scripts (`de0-cv_synth.tcl`, `de0-cv_program.sh`) are kept
as fixtures: the new path must do what they do.
"""

import argparse
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from multifpga_support import FIXTURES
from support import (
    check,
    check_equal,
    check_in,
    check_not_in,
    write_config,
)

from riscv_tools import board_generate, quartus_program
from riscv_tools.board_generate import Generated, ProjectRequest, ProjectResult
from riscv_tools.cli import board_cmd
from riscv_tools.jtag import JtagLink
from riscv_tools.quartus_program import (
    CompileOptions,
    QuartusProject,
    compile_command,
    full_reconfigure,
    parse_generics,
    program_only,
)
from riscv_tools.quartus_program import core as program_core

HAND = FIXTURES / "handwritten"
TCLSH = shutil.which("tclsh")


def _tclsh() -> str:
    """Return the tclsh path, or skip the test without one."""
    if TCLSH is None:
        pytest.skip("tclsh not installed")
    return TCLSH


DRIVER = textwrap.dedent(
    """\
    set log {}
    foreach cmd {load_package project_open set_global_assignment set_parameter
                 execute_module execute_flow project_close} {
        proc $cmd {args} "global log; lappend log \\"$cmd \\$args\\""
    }
    set quartus(args) [split $env(ARGS) " "]
    if {$env(ARGS) eq ""} {set quartus(args) {}}
    set argc [llength $quartus(args)]
    source $env(SCRIPT)
    puts [join $log "\\n"]
    """
)


def _tcl_log(script: Path, args: str, tmp: Path) -> list[str]:
    """Run a Quartus Tcl script under tclsh with recording stubs."""
    driver = tmp / "driver.tcl"
    driver.write_text(DRIVER)
    done = subprocess.run(
        [_tclsh(), str(driver)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "ARGS": args, "SCRIPT": str(script)},
    )
    check_equal(done.returncode, 0, done.stdout + done.stderr)
    return done.stdout.splitlines()


@pytest.mark.skipif(TCLSH is None, reason="tclsh not installed")
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("", "de0-cv 5 full"),
        ("7", "de0-cv 7 full"),
        ("5 map", "de0-cv 5 map"),
        (
            "3 map HPM_COUNTERS=4 HPM_WIDTH=40",
            "de0-cv 3 map HPM_COUNTERS=4 HPM_WIDTH=40",
        ),
        ("5 HPM_WIDTH=40", "de0-cv 5 full HPM_WIDTH=40"),
    ],
)
def test_the_compile_script_does_what_the_synth_script_does(
    tmp_path: Path, old: str, new: str
) -> None:
    """The recorded Quartus calls are the same for the DE0-CV."""
    shutil.copy(HAND / "de0-cv_synth.tcl", tmp_path / "de0-cv_synth.tcl")
    before = _tcl_log(tmp_path / "de0-cv_synth.tcl", old, tmp_path)
    after = _tcl_log(program_core.COMPILE_TCL, new, tmp_path)
    check_equal(after, before)
    check_in("project_open de0-cv", after)


@pytest.mark.skipif(TCLSH is None, reason="tclsh not installed")
def test_fit_and_sta_run_the_stages_in_order(tmp_path: Path) -> None:
    """`fit` adds the fitter and `sta` adds the timing analysis."""
    fit = _tcl_log(program_core.COMPILE_TCL, "p 5 fit", tmp_path)
    sta = _tcl_log(program_core.COMPILE_TCL, "p 5 sta", tmp_path)
    check_equal(
        fit[-3:-1], ["execute_module -tool map", "execute_module -tool fit"]
    )
    check_equal(
        sta[-4:-1],
        [
            "execute_module -tool map",
            "execute_module -tool fit",
            "execute_module -tool sta",
        ],
    )


@pytest.mark.skipif(TCLSH is None, reason="tclsh not installed")
@pytest.mark.parametrize("args", ["p 0 map", "p 5 nope", "p 5 map X", "p"])
def test_the_compile_script_refuses_bad_arguments(
    tmp_path: Path, args: str
) -> None:
    """Seed, stop point, generics and arity are validated."""
    driver = tmp_path / "driver.tcl"
    driver.write_text(DRIVER)
    done = subprocess.run(
        [_tclsh(), str(driver)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "ARGS": args,
            "SCRIPT": str(program_core.COMPILE_TCL),
        },
    )
    check_equal(done.returncode, 2)
    check_in("Erro", done.stdout)


def test_the_compile_command_without_options_is_the_direct_flow() -> None:
    """Without new options the compile is exactly what it was."""
    check_equal(
        compile_command("de0-cv", CompileOptions()),
        ["quartus_sh", "--flow", "compile", "de0-cv"],
    )
    check_equal(
        compile_command("de0-cv", CompileOptions(compile_only=True)),
        ["quartus_sh", "--flow", "compile", "de0-cv"],
    )


def test_the_compile_command_with_options_uses_the_script() -> None:
    """Seed, generics and stop point go to the single script."""
    command = compile_command(
        "p",
        CompileOptions(
            seed=3, generics=(("HPM_WIDTH", 40),), stop_after="map"
        ),
    )
    check_equal(
        command[:3], ["quartus_sh", "-t", str(program_core.COMPILE_TCL)]
    )
    check_equal(command[3:], ["p", "3", "map", "HPM_WIDTH=40"])
    check_equal(
        compile_command("p", CompileOptions(stop_after="fit"))[4:6],
        ["5", "fit"],
    )


def test_generics_are_parsed_and_checked() -> None:
    """Only NAME=INTEGER is accepted."""
    check_equal(parse_generics(["A=1", "B_2=30"]), (("A", 1), ("B_2", 30)))
    with pytest.raises(ValueError, match="NAME=INTEGER"):
        parse_generics(["A=x"])


def test_programming_follows_the_options() -> None:
    """Compile-only and any stop point skip the programmer."""
    check(CompileOptions().programs)
    check(CompileOptions(seed=4).programs)
    check(not CompileOptions(compile_only=True).programs)
    check(not CompileOptions(stop_after="map").programs)


def test_the_chain_compiles_then_programs_unless_compile_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One `bash -c` chain, with the programmer only when asked."""
    seen: list[list[str]] = []
    monkeypatch.setattr(program_core, "_run_captured", seen.append)
    project = QuartusProject(
        "USB-Blaster [1-2]", tmp_path, "de0-cv", "x.sof", []
    )
    full_reconfigure(project, None)
    check_in("quartus_pgm", seen[-1][-1])
    full_reconfigure(project, None, options=CompileOptions(compile_only=True))
    check_not_in("quartus_pgm", seen[-1][-1])
    full_reconfigure(project, None, options=CompileOptions(seed=9))
    check_in("compile.tcl de0-cv 9 full", seen[-1][-1])
    check_in("quartus_pgm", seen[-1][-1])


def _fake_tools(directory: Path, log: Path) -> None:
    """Put a fake `jtagconfig` and `quartus_pgm` ahead on PATH."""
    directory.mkdir()
    (directory / "jtagconfig").write_text(
        "#!/bin/sh\necho '1) USB-Blaster [1-2]'\n"
        "echo '  02B050DD   5CE(BA4|FA4)'\n"
    )
    (directory / "quartus_pgm").write_text(f'#!/bin/sh\necho "$@" > {log}\n')
    for tool in directory.iterdir():
        tool.chmod(0o755)


def test_program_only_runs_what_the_program_script_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same `quartus_pgm` arguments as the old script, same cable."""
    bin_dir = tmp_path / "bin"
    old_log, new_log = tmp_path / "old.log", tmp_path / "new.log"
    _fake_tools(bin_dir, old_log)
    project = tmp_path / "proj"
    (project / "output_files").mkdir(parents=True)
    (project / "output_files" / "de0-cv.sof").write_text("sof")
    shutil.copy(HAND / "de0-cv_program.sh", project / "de0-cv_program.sh")
    path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    subprocess.run(
        ["bash", str(project / "de0-cv_program.sh")],
        check=True,
        capture_output=True,
        env={**os.environ, "PATH": path},
    )
    _fake_tools(tmp_path / "bin2", new_log)
    monkeypatch.setenv(
        "PATH", f"{tmp_path / 'bin2'}{os.pathsep}{os.environ['PATH']}"
    )
    program_only("USB-Blaster [1-2]", project, "output_files/de0-cv.sof")
    check_equal(
        new_log.read_text().replace(str(project) + "/", ""),
        old_log.read_text(),
    )


def _config(tmp_path: Path) -> Path:
    """Write the config of a project with a Quartus section."""
    write_config(
        tmp_path,
        {
            "quartus": {
                "project_dir": "proj",
                "project_name": "de0-cv",
                "sof_file": "output_files/de0-cv.sof",
                "rom_mif_target": "rom.mif",
                "jtag_device": "@1: 5CE(BA4|FA4) (0x02B050DD)",
            }
        },
    )
    return tmp_path / "config.yaml"


def _args(tmp_path: Path, **changes: object) -> argparse.Namespace:
    """Build the arguments of `program`."""
    base: dict[str, object] = {
        "config": str(_config(tmp_path)),
        "root": str(tmp_path),
        "mif": None,
        "project_dir": None,
        "project_name": None,
        "seed": None,
        "generic": [],
        "stop_after": None,
        "compile_only": False,
    }
    return argparse.Namespace(**(base | changes))


def test_program_compile_only_needs_no_mif_and_no_cable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A compile-only run detects no cable."""
    calls: list[tuple[QuartusProject, CompileOptions]] = []

    def fake(
        project: QuartusProject,
        options: CompileOptions | None = None,
        **_other: object,
    ) -> None:
        calls.append((project, options or CompileOptions()))

    monkeypatch.setattr(quartus_program, "full_reconfigure", fake)

    def no_cable(*_args: object) -> str:
        pytest.fail("no cable expected")

    monkeypatch.setattr(board_cmd, "jtag_link", no_cable)
    board_cmd.cmd_program(
        _args(tmp_path, compile_only=True, seed=4, generic=["HPM_COUNTERS=4"])
    )
    project, options = calls[0]
    check_equal(project.hardware_name, "")
    check_equal(project.project_dir, tmp_path / "proj")
    check_equal(options.seed, 4)
    check_equal(options.generics, (("HPM_COUNTERS", 4),))


def test_program_programs_through_the_selected_cable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Programming takes the cable the board selection picked."""
    calls: list[QuartusProject] = []

    def link(_cfg: object) -> JtagLink:
        return JtagLink("USB-Blaster [1-2]", "dev", 0)

    def record(project: QuartusProject, *_args: object, **_kw: object) -> None:
        calls.append(project)

    monkeypatch.setattr(board_cmd, "jtag_link", link)
    monkeypatch.setattr(quartus_program, "full_reconfigure", record)
    board_cmd.cmd_program(_args(tmp_path, mif="rom.mif"))
    check_equal(calls[0].hardware_name, "USB-Blaster [1-2]")


def test_program_without_mif_or_compile_only_fails(tmp_path: Path) -> None:
    """Programming needs the image."""
    with pytest.raises(SystemExit):
        board_cmd.cmd_program(_args(tmp_path))


def test_program_writes_the_generated_project_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `quartus.generate` the project is written, then compiled."""
    order: list[str] = []
    seen: list[ProjectRequest] = []

    def built(request: ProjectRequest) -> ProjectResult:
        order.append("generate")
        seen.append(request)
        return ProjectResult(Generated("p", "p", {}), tmp_path / "build" / "p")

    def compiled(*_args: object, **_kw: object) -> None:
        order.append("compile")

    monkeypatch.setattr(board_generate, "build", built)
    monkeypatch.setattr(quartus_program, "full_reconfigure", compiled)
    args = _args(tmp_path, compile_only=True, seed=3)
    write_config(
        tmp_path,
        {
            "quartus": {
                "project_dir": "build/p",
                "project_name": "p",
                "sof_file": "output_files/p.sof",
                "rom_mif_target": "rom.mif",
                "generate": {"platform": "plat.yaml", "out": "build"},
            }
        },
    )
    board_cmd.cmd_program(args)
    check_equal(order, ["generate", "compile"])
    check_equal(seen[0].platform, "plat.yaml")
    check_equal(seen[0].out, "build")
    check_equal(seen[0].seed, 3)
