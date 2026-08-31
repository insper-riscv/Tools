"""Compile the whole Quartus project and program the board — the slow "base" path."""

import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _run_captured(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, always capturing text output and printing it through.

    Same rationale as jtag.link.run: a subprocess.CalledProcessError
    raised from here always carries real .stdout/.stderr text (e.g.
    "Can't scan JTAG chain") a caller can classify — see
    orchestrator.runner's hardware-failure classifier — instead of the
    None/None a plain `subprocess.run(cmd, check=True)` leaves on its
    exception.
    """
    print("+", " ".join(str(c) for c in cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        raise
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def program_only(hardware_name: str, project_dir: Path, sof_file: str) -> None:
    """Reprogram the board from the EXISTING .sof, no recompile.

    Much cheaper than full_reconfigure (~10s vs the several minutes a
    full `quartus_sh --flow compile` takes) — worth trying first when
    a test's mailbox times out, in the same-frequency test suite
    specifically: the design itself never changes between tests there
    (only the ROM content, which gets reloaded over JTAG separately by
    rom_writer, not baked in at compile time) — so a wedged board most
    likely just needs a fresh `quartus_pgm`, not a fresh compile of a
    bitstream that would come out identical anyway. Only recompile
    (full_reconfigure) if this doesn't get the board responding again.

    Whatever ROM content happens to be baked into this .sof (from
    whichever test's compile last ran) is what the board boots with
    after this — the caller still needs to JTAG-write the CURRENT
    test's ROM and pulse the restart flag afterward (see
    orchestrator.run_test_via_jtag), same as after any other reprogram.

    Parameters
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware) — pinned explicitly via
        quartus_pgm's -c so a second board's cable can't be picked by
        mistake.
    project_dir : Path
        Path to the Quartus project directory (quartus.project_dir in
        the project's config.yaml).
    sof_file : str
        Path (relative to project_dir) to the compiled .sof, passed to
        quartus_pgm (quartus.sof_file).

    Returns
    -------
    None

    Raises
    ------
    FileNotFoundError
        sof_file doesn't exist (e.g. a previous full_reconfigure got
        interrupted after its stale_cache_dirs cleanup but before the
        Assembler produced a new one) — nothing to reprogram from,
        caller should fall back to full_reconfigure instead.
    """
    sof_path = project_dir / sof_file
    if not sof_path.is_file():
        raise FileNotFoundError(
            f"{sof_path} does not exist — need a full compile first"
        )
    pgm_cmd = [
        "quartus_pgm",
        "-c",
        hardware_name,
        "-m",
        "JTAG",
        "-o",
        f"p;{sof_path}",
    ]
    _run_captured(pgm_cmd)


# Each arg is an independent Quartus project setting — not bundleable
# without a config object this module doesn't otherwise need.
def full_reconfigure(  # noqa: PLR0913, PLR0917
    hardware_name: str,
    project_dir: Path,
    project_name: str,
    sof_file: str,
    rom_mif_target: str,
    stale_cache_dirs: list[str],
    rom_mif_path: Path,
) -> None:
    """Compile the whole Quartus project and program the board.

    Bakes rom_mif_path in as the ROM's init_file, then programs the
    board — the slow path. Meant to run once up front to establish a
    baseline bitstream, and again as a fallback if a JTAG-reloaded
    test (rom_writer + mailbox) times out, in case the board itself
    wedged rather than the test hanging.

    Parameters
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware) — pinned explicitly via
        quartus_pgm's -c so a second board's cable can't be picked by
        mistake.
    project_dir : Path
        Path to the Quartus project directory (quartus.project_dir in
        the project's config.yaml).
    project_name : str
        Quartus project/revision name passed to `quartus_sh --flow
        compile` (quartus.project_name).
    sof_file : str
        Path (relative to project_dir) to the compiled .sof, passed to
        quartus_pgm (quartus.sof_file).
    rom_mif_target : str
        Path (relative to project_dir) the ROM megafunction reads its
        init_file from at compile time — rom_mif_path is copied here
        before compiling (quartus.rom_mif_target).
    stale_cache_dirs : list of str
        Directory names (relative to project_dir) to delete before
        compiling, since Quartus' incremental build cache doesn't
        track init_file content as a project source
        (quartus.stale_cache_dirs).
    rom_mif_path : Path
        Path to the .mif to bake in as the ROM's initial content for
        this compile.

    Returns
    -------
    None
    """
    rom_target = project_dir / rom_mif_target
    rom_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(rom_mif_path, rom_target)

    for stale in stale_cache_dirs:
        shutil.rmtree(project_dir / stale, ignore_errors=True)

    # compile and program are shelled out as ONE bash -c chain, not two
    # separate subprocess.run() calls, because invoking quartus_pgm as
    # its own Python-launched subprocess right after quartus_sh
    # reliably reports "Can't scan JTAG chain" (error 87) — reproduced
    # 4/4 times through this module's own subprocess.run() sequence
    # (with delays from 0s to 10s between the two calls — delay length
    # made no difference), while chaining the exact same two commands
    # in a single shell process (this project's own manual
    # `quartus_sh ...; quartus_pgm ...` in one `bash -c`, even with a
    # ~1s gap) succeeded 2/2 times. The cause isn't confirmed, but the
    # workaround is reproducible: keep both commands in one shell
    # process, not two Python subprocess.run() calls.
    compile_cmd = ["quartus_sh", "--flow", "compile", project_name]
    pgm_cmd = [
        "quartus_pgm",
        "-c",
        hardware_name,
        "-m",
        "JTAG",
        "-o",
        f"p;{project_dir / sof_file}",
    ]
    script = (
        f"cd {shlex.quote(str(project_dir))} && {shlex.join(compile_cmd)} && "
        f"{shlex.join(pgm_cmd)}"
    )
    _run_captured(["bash", "-c", script])
