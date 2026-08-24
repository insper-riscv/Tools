import shutil
import subprocess
from pathlib import Path

from riscv_tools.jtag import run


def full_reconfigure(
    hardware_name: str,
    project_dir: Path,
    project_name: str,
    sof_file: str,
    rom_mif_target: str,
    stale_cache_dirs: list[str],
    rom_mif_path: Path,
) -> None:
    """Compiles the whole Quartus project with rom_mif_path baked in
    as the ROM's init_file, then programs the board — the slow path.
    Meant to run once up front to establish a baseline bitstream, and
    again as a fallback if a JTAG-reloaded test (rom_writer + mailbox)
    times out, in case the board itself wedged rather than the test
    hanging."""
    rom_target = project_dir / rom_mif_target
    rom_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(rom_mif_path, rom_target)

    for stale in stale_cache_dirs:
        shutil.rmtree(project_dir / stale, ignore_errors=True)

    run(["quartus_sh", "--flow", "compile", project_name], cwd=project_dir)
    # -c pins the cable explicitly: with a second board's blaster also
    # enumerated, letting quartus_pgm guess is not safe.
    run(["quartus_pgm", "-c", hardware_name, "-m", "JTAG", "-o", f"p;{project_dir / sof_file}"])
