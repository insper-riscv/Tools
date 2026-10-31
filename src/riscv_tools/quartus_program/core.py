"""Compile the whole Quartus project and program the board (slow)."""

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.proc import run_streaming

# Thin alias: this module's own callers/docs refer to "_run_captured";
# see riscv_tools.proc.run_streaming for the streaming/classification
# rationale, shared with jtag.link.run.
_run_captured = run_streaming


def program_only(hardware_name: str, project_dir: Path, sof_file: str) -> None:
    """Reprogram the board from the EXISTING .sof, no recompile.

    Much cheaper than full_reconfigure (~10s vs the several minutes a
    full `quartus_sh --flow compile` takes), worth trying first when
    a test's mailbox times out, in the same-frequency test suite
    specifically: the design itself never changes between tests there
    (only the ROM content, which gets reloaded over JTAG separately by
    rom_writer, not baked in at compile time), so a wedged board most
    likely just needs a fresh `quartus_pgm`, not a fresh compile of a
    bitstream that would come out identical anyway. Only recompile
    (full_reconfigure) if this doesn't get the board responding again.

    Whatever ROM content happens to be baked into this .sof (from
    whichever test's compile last ran) is what the board boots with
    after this; the caller still needs to JTAG-write the CURRENT
    test's ROM and pulse the restart flag afterward (see
    orchestrator.run_test_via_jtag), same as after any other reprogram.

    Parameters
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware), pinned explicitly via
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
        Assembler produced a new one); nothing to reprogram from,
        caller should fall back to full_reconfigure instead.
    """
    sof_path = project_dir / sof_file
    if not sof_path.is_file():
        raise FileNotFoundError(
            f"{sof_path} does not exist; need a full compile first"
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


@dataclass(frozen=True)
class QuartusProject:
    """The Quartus project settings a full compile and program needs.

    Attributes
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware), pinned explicitly via quartus_pgm's
        -c so a second board's cable can't be picked by mistake.
    project_dir : Path
        Path to the Quartus project directory (quartus.project_dir in
        the project's config.yaml).
    project_name : str
        Quartus project/revision name passed to `quartus_sh --flow
        compile` (quartus.project_name).
    sof_file : str
        Path (relative to project_dir) to the compiled .sof, passed to
        quartus_pgm (quartus.sof_file).
    stale_cache_dirs : list of str
        Directory names (relative to project_dir) to delete before
        compiling, since Quartus' incremental build cache doesn't
        track init_file content as a project source
        (quartus.stale_cache_dirs).
    """

    hardware_name: str
    project_dir: Path
    project_name: str
    sof_file: str
    stale_cache_dirs: list[str]


@dataclass(frozen=True)
class MifInit:
    """A .mif baked in as a memory's initial content.

    Attributes
    ----------
    target : str
        Path (relative to project_dir) the memory megafunction reads
        its init_file from at compile time (e.g.
        quartus.rom_mif_target); `path` is copied here before
        compiling.
    path : Path
        Path to the .mif to bake in as the memory's initial content.
    """

    target: str
    path: Path


def full_reconfigure(
    project: QuartusProject,
    rom: MifInit,
    boot_rom: MifInit | None = None,
) -> None:
    """Compile the whole Quartus project and program the board.

    Bakes rom.path in as the ROM's init_file, then programs the
    board, the slow path. Meant to run once up front to establish a
    baseline bitstream, and again as a fallback if a JTAG-reloaded
    test (rom_writer + mailbox) times out, in case the board itself
    wedged rather than the test hanging.

    Parameters
    ----------
    project : QuartusProject
        The Quartus project to compile and program.
    rom : MifInit
        The .mif to bake in as the ROM's initial content.
    boot_rom : MifInit, optional
        The .mif to bake in as the shared bootloader's initial content
        (quartus.boot_rom_mif_target), only for a project with a
        BOOT_ROM/FLASH/RAM split. It is written only by this full
        compile, never per test.

    Returns
    -------
    None
    """
    project_dir = project.project_dir
    for init in (rom, boot_rom):
        if init is not None:
            target = project_dir / init.target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(init.path, target)

    for stale in project.stale_cache_dirs:
        shutil.rmtree(project_dir / stale, ignore_errors=True)

    # Compile and program run as ONE bash -c chain, not as two
    # subprocess.run() calls: quartus_pgm launched on its own right
    # after quartus_sh fails with "Can't scan JTAG chain" (error 87),
    # whatever the delay between the two, while the same two commands
    # in a single shell succeed.
    compile_cmd = ["quartus_sh", "--flow", "compile", project.project_name]
    pgm_cmd = [
        "quartus_pgm",
        "-c",
        project.hardware_name,
        "-m",
        "JTAG",
        "-o",
        f"p;{project_dir / project.sof_file}",
    ]
    script = (
        f"cd {shlex.quote(str(project_dir))} && {shlex.join(compile_cmd)} && "
        f"{shlex.join(pgm_cmd)}"
    )
    _run_captured(["bash", "-c", script])
