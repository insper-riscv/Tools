"""Run one test on the programmed board and reprogram it."""

import time
from pathlib import Path
from typing import Any

from riscv_tools import (
    mailbox,
    quartus_program,
    rom_writer,
)
from riscv_tools.jtag import JtagLink


def run_test_via_jtag(
    cfg: dict[str, Any], link: JtagLink, entry: dict[str, Any], root: Path
) -> int | None:
    """Load the ROM of entry, pulse the restart flag, poll the mailbox.

    It works on the already-programmed board and polls up to entry's
    timeout_s.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config (see settings.load_config): uses
        quartus.rom_mem_instances/ram_mem_instance/
        poll_interval_seconds and memory.ram_base/go_flag_addr/
        mailbox_addr.
    link : JtagLink
        Which JTAG cable/chip to use.
    entry : dict of {str: Any}
        One manifest entry (from compile --emit mif): uses "mif"
        (path, relative to root) and "timeout_s".
    root : Path
        The consuming project's root directory, entry["mif"] is
        relative to this.

    Returns
    -------
    int or None
        The mailbox value (mailbox.PASS or mailbox.FAIL) once the test
        signals completion, or None if entry["timeout_s"] elapses
        first.
    """
    # The core is parked after the previous test: clear its mailbox
    # first, so the host never mistakes that test's result for this
    # one's.
    mailbox.clear_configured(link, cfg)
    rom_writer.write_rom(
        link, cfg["quartus"]["rom_mem_instances"], root / entry["mif"]
    )
    mailbox.pulse_configured(link, cfg)

    poll_s = cfg["quartus"]["poll_interval_seconds"]
    deadline = time.monotonic() + entry["timeout_s"]
    while time.monotonic() < deadline:
        value = mailbox.read_configured(link, cfg)
        if value in (mailbox.PASS, mailbox.FAIL):
            return value
        time.sleep(poll_s)
    return None


def reconfigure_with_rom(
    cfg: dict[str, Any], link: JtagLink, project_dir: Path, mif_path: Path
) -> None:
    """Recompile the project with a ROM image baked in and program it.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses its `quartus` section.
    link : JtagLink
        Which JTAG cable/chip to program.
    project_dir : Path
        Path to the Quartus project directory.
    mif_path : Path
        The .mif to initialize the ROM with.

    Raises
    ------
    subprocess.CalledProcessError
        The Quartus compile or the programming failed.
    """
    quartus_program.full_reconfigure(
        project=quartus_program.QuartusProject(
            hardware_name=link.hardware_name,
            project_dir=project_dir,
            project_name=cfg["quartus"]["project_name"],
            sof_file=cfg["quartus"]["sof_file"],
            stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        ),
        rom=quartus_program.MifInit(
            target=cfg["quartus"]["rom_mif_target"],
            path=mif_path,
        ),
    )


def full_reconfigure_entry(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> None:
    """Pull the arguments of full_reconfigure out of cfg/entry.

    They are the arguments of quartus_program.full_reconfigure.

    Thin adapter so callers don't have to.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: uses
        quartus.project_name/sof_file/rom_mif_target/
        stale_cache_dirs.
    link : JtagLink
        Which JTAG cable/chip to program.
    entry : dict of {str: Any}
        One manifest entry: uses "mif" (path, relative to root) as
        the ROM content to bake in.
    root : Path
        The consuming project's root directory, entry["mif"] is
        relative to this.
    project_dir : Path
        Path to the Quartus project directory.

    Returns
    -------
    None
    """
    reconfigure_with_rom(cfg, link, project_dir, root / entry["mif"])
