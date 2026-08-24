"""Compile the whole Quartus project and program the board — the slow "base" path."""

import shutil
from pathlib import Path

from riscv_tools.jtag import run


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

    run(["quartus_sh", "--flow", "compile", project_name], cwd=project_dir)
    # -c pins the cable explicitly: with a second board's blaster also
    # enumerated, letting quartus_pgm guess is not safe.
    run(
        [
            "quartus_pgm",
            "-c",
            hardware_name,
            "-m",
            "JTAG",
            "-o",
            f"p;{project_dir / sof_file}",
        ]
    )
