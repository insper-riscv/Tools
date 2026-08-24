"""Composes the other modules into a full real-hardware test run:
compile once (quartus_program), then per test JTAG-write ROM
(rom_writer) + pulse restart (mailbox) + poll for PASS/FAIL (mailbox),
falling back to a full recompile+reprogram if a test's mailbox never
responds within its timeout. Owns no hardware mechanism itself — only
sequencing."""
import time
from pathlib import Path

from riscv_tools import mailbox, mem_validator, quartus_program, ram_dump, rom_writer
from riscv_tools.jtag import JtagLink


def run_test_via_jtag(cfg: dict, link: JtagLink, entry: dict, root: Path) -> int | None:
    """Loads entry's ROM and pulses the restart flag on the already-
    programmed board, then polls the mailbox up to entry's timeout_s.
    Returns the mailbox value (mailbox.PASS/mailbox.FAIL) or None on
    timeout."""
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instance"], root / entry["mif"])
    mailbox.pulse_go_flag(
        link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_base"], cfg["memory"]["go_flag_addr"]
    )

    poll_s = cfg["quartus"]["poll_interval_seconds"]
    deadline = time.monotonic() + entry["timeout_s"]
    while time.monotonic() < deadline:
        value = mailbox.read_mailbox(
            link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_base"], cfg["memory"]["mailbox_addr"]
        )
        if value in (mailbox.PASS, mailbox.FAIL):
            return value
        time.sleep(poll_s)
    return None


def full_reconfigure_entry(cfg: dict, link: JtagLink, entry: dict, root: Path, project_dir: Path) -> None:
    quartus_program.full_reconfigure(
        hardware_name=link.hardware_name,
        project_dir=project_dir,
        project_name=cfg["quartus"]["project_name"],
        sof_file=cfg["quartus"]["sof_file"],
        rom_mif_target=cfg["quartus"]["rom_mif_target"],
        stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        rom_mif_path=root / entry["mif"],
    )


def run_one(cfg: dict, link: JtagLink, entry: dict, build_dir: Path, root: Path, project_dir: Path) -> bool:
    name = entry["name"]
    print(f"\n=== {name} ({entry['march']}, {entry['kind']}, timeout={entry['timeout_s']}s) ===")

    value = run_test_via_jtag(cfg, link, entry, root)
    if value is None:
        print(
            f"{name}: no mailbox result after {entry['timeout_s']}s; the board may have "
            "wedged (e.g. a dropped JTAG chain) rather than the test hanging — "
            "falling back to a full recompile+reprogram+retry"
        )
        full_reconfigure_entry(cfg, link, entry, root, project_dir)
        wait_s = cfg["quartus"]["program_wait_seconds"]
        print(f"Waiting {wait_s}s for the program to run ...")
        time.sleep(wait_s)
        value = mailbox.read_mailbox(
            link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_base"], cfg["memory"]["mailbox_addr"]
        )

    if value == mailbox.PASS:
        print(f"{name}: PASS")
        passed = True
    elif value == mailbox.FAIL:
        print(f"{name}: FAIL")
        passed = False
    else:
        print(f"{name}: TIMEOUT/UNKNOWN (mailbox={value}); program may not have finished")
        passed = False

    if entry["kind"] == "integration":
        dump_path = build_dir / f"{name}_ram.mif"
        ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], dump_path)
        passed = mem_validator.compare(dump_path, root / entry["golden"]) and passed

    return passed


def run_suite(
    cfg: dict, link: JtagLink, manifest: list[dict], build_dir: Path, root: Path, project_dir: Path
) -> dict[str, bool]:
    if not manifest:
        raise ValueError("Manifest is empty; nothing to run")

    print("Compiling and programming the board once ...")
    full_reconfigure_entry(cfg, link, manifest[0], root, project_dir)

    return {entry["name"]: run_one(cfg, link, entry, build_dir, root, project_dir) for entry in manifest}
