"""Compose the other modules into a full real-hardware test run.

Two flows:

- The fixed-frequency test suite: compiles once (quartus_program),
  then per test JTAG-writes ROM (rom_writer) + pulses restart
  (mailbox) + polls for PASS/FAIL (mailbox), falling back to a full
  recompile+reprogram if a test's mailbox never responds within its
  timeout (see run_suite/run_one).
- The clock frequency sweep: edits the project's PLL (freq_sweep) and
  does a full recompile+reprogram+RAM-compare at each candidate
  frequency, since a clock frequency is baked in at synthesis time —
  there's no faster JTAG-reload path here the way there is for
  same-frequency tests (see run_freq_sweep_linear/
  run_freq_sweep_binary).

Owns no hardware mechanism itself — only sequencing.
"""

import subprocess
import time
from pathlib import Path
from typing import Any

from riscv_tools import (
    freq_sweep,
    mailbox,
    mem_validator,
    quartus_program,
    ram_dump,
    rom_writer,
)
from riscv_tools.jtag import JtagLink

# run_freq_sweep_linear stops once this many consecutive candidates
# fail — past that point the board is assumed to already be beyond
# Fmax, so continuing just burns more full-reconfigure cycles for no
# new information.
_CONSECUTIVE_FAILS_TO_STOP = 3


def run_test_via_jtag(
    cfg: dict[str, Any], link: JtagLink, entry: dict[str, Any], root: Path
) -> int | None:
    """Load entry's ROM and pulse the restart flag, then poll the mailbox.

    Loads entry's ROM and pulses the restart flag on the
    already-programmed board, then polls the mailbox up to entry's
    timeout_s.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config (see settings.load_config) — uses
        quartus.rom_mem_instance/ram_mem_instance/
        poll_interval_seconds and memory.ram_base/go_flag_addr/
        mailbox_addr.
    link : JtagLink
        Which JTAG cable/chip to use.
    entry : dict of {str: Any}
        One manifest entry (from compile --emit mif) — uses "mif"
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
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instance"], root / entry["mif"])
    mailbox.pulse_go_flag(
        link,
        cfg["quartus"]["ram_mem_instance"],
        cfg["memory"]["ram_base"],
        cfg["memory"]["go_flag_addr"],
    )

    poll_s = cfg["quartus"]["poll_interval_seconds"]
    deadline = time.monotonic() + entry["timeout_s"]
    while time.monotonic() < deadline:
        value = mailbox.read_mailbox(
            link,
            cfg["quartus"]["ram_mem_instance"],
            cfg["memory"]["ram_base"],
            cfg["memory"]["mailbox_addr"],
        )
        if value in (mailbox.PASS, mailbox.FAIL):
            return value
        time.sleep(poll_s)
    return None


def full_reconfigure_entry(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> None:
    """Pull quartus_program.full_reconfigure's arguments out of cfg/entry.

    Thin adapter so callers don't have to.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses
        quartus.project_name/sof_file/rom_mif_target/
        stale_cache_dirs.
    link : JtagLink
        Which JTAG cable/chip to program.
    entry : dict of {str: Any}
        One manifest entry — uses "mif" (path, relative to root) as
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
    quartus_program.full_reconfigure(
        hardware_name=link.hardware_name,
        project_dir=project_dir,
        project_name=cfg["quartus"]["project_name"],
        sof_file=cfg["quartus"]["sof_file"],
        rom_mif_target=cfg["quartus"]["rom_mif_target"],
        stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        rom_mif_path=root / entry["mif"],
    )


# cfg/link/entry/build_dir/root/project_dir are each an independent
# piece of orchestration state — not bundleable without a wrapper
# object this module doesn't otherwise need.
def run_one(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    build_dir: Path,
    root: Path,
    project_dir: Path,
) -> bool:
    """Run a single test end to end.

    JTAG-reload + poll (see run_test_via_jtag), falling back to a full
    reconfigure + retry on timeout, then a RAM-vs-golden compare if
    entry is a "memory" test.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — see run_test_via_jtag and
        full_reconfigure_entry for the fields used, plus
        quartus.program_wait_seconds (wait after the fallback
        reconfigure).
    link : JtagLink
        Which JTAG cable/chip to use.
    entry : dict of {str: Any}
        One manifest entry — uses "name", "march", "kind",
        "timeout_s", "mif", and (for "memory" tests) "golden".
    build_dir : Path
        Directory to write this test's RAM dump into
        (build_dir/<name>_ram.mif), for "memory" tests.
    root : Path
        The consuming project's root directory, entry["mif"]/
        entry["golden"] are relative to this.
    project_dir : Path
        Path to the Quartus project directory, used only if the
        JTAG-reload path times out.

    Returns
    -------
    bool
        True if the test passed (mailbox PASS, and the RAM-vs-golden
        compare if applicable), False otherwise.
    """
    name = entry["name"]
    print(
        f"\n=== {name} ({entry['march']}, {entry['kind']}, "
        f"timeout={entry['timeout_s']}s) ==="
    )

    value = run_test_via_jtag(cfg, link, entry, root)
    if value is None:
        print(
            f"{name}: no mailbox result after {entry['timeout_s']}s; "
            "the board may have wedged (e.g. a dropped JTAG chain) "
            "rather than the test hanging — falling back to a full "
            "recompile+reprogram+retry"
        )
        full_reconfigure_entry(cfg, link, entry, root, project_dir)
        wait_s = cfg["quartus"]["program_wait_seconds"]
        print(f"Waiting {wait_s}s for the program to run ...")
        time.sleep(wait_s)
        value = mailbox.read_mailbox(
            link,
            cfg["quartus"]["ram_mem_instance"],
            cfg["memory"]["ram_base"],
            cfg["memory"]["mailbox_addr"],
        )

    if value == mailbox.PASS:
        print(f"{name}: PASS")
        passed = True
    elif value == mailbox.FAIL:
        print(f"{name}: FAIL")
        passed = False
    else:
        print(
            f"{name}: TIMEOUT/UNKNOWN (mailbox={value}); program may not have finished"
        )
        passed = False

    if entry["kind"] == "memory":
        dump_path = build_dir / f"{name}_ram.mif"
        ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], dump_path)
        passed = mem_validator.compare(dump_path, root / entry["golden"]) and passed

    return passed


# Same rationale as run_one above: each arg is independent
# orchestration state.
def run_suite(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    manifest: list[dict[str, Any]],
    build_dir: Path,
    root: Path,
    project_dir: Path,
    *,
    reconfigure: bool = True,
) -> dict[str, bool]:
    """Run every test in manifest against real hardware.

    Compiles and programs the board once, then runs each entry via
    run_one.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config, forwarded to
        full_reconfigure_entry/run_one.
    link : JtagLink
        Which JTAG cable/chip to use.
    manifest : list of dict of {str: Any}
        The test list to run (typically compile --emit mif's full
        manifest.json, but may be a caller-filtered subset — see
        cli.cmd_run's --only) — must be non-empty; when reconfigure is
        True, manifest[0]'s ROM is what gets baked into the initial
        compile.
    build_dir : Path
        Forwarded to run_one (RAM dump output directory).
    root : Path
        The consuming project's root directory, forwarded to
        run_one/full_reconfigure_entry.
    project_dir : Path
        Path to the Quartus project directory, forwarded to
        run_one/full_reconfigure_entry.
    reconfigure : bool, keyword-only, optional
        If True (the default), compile+program the board once via
        full_reconfigure_entry before running any test — the normal,
        safe-by-default path, needed whenever the board isn't known to
        already be running a compatible bitstream. If False, skip
        straight to run_one for every entry, assuming the board is
        ALREADY correctly programmed (e.g. re-running a handful of
        tests that failed earlier in the same session, via --only,
        without wanting to risk another compile+quartus_pgm cycle —
        see HARDWARE_PROGRAMMING.md for why that step is the fragile
        one). Getting this wrong (board not actually programmed, or
        programmed with an incompatible/stale bitstream) looks like
        every test timing out waiting for its mailbox, not a clean
        error — only pass False when you're sure.

    Returns
    -------
    dict of {str: bool}
        A {test_name: passed} dict, one entry per manifest test, in
        manifest order.

    Raises
    ------
    ValueError
        manifest is empty.
    """
    if not manifest:
        raise ValueError("Manifest is empty; nothing to run")

    if reconfigure:
        print("Compiling and programming the board once ...")
        full_reconfigure_entry(cfg, link, manifest[0], root, project_dir)

    return {
        entry["name"]: run_one(cfg, link, entry, build_dir, root, project_dir)
        for entry in manifest
    }


# cfg/link/mif_path/golden_path/project_dir/build_dir are each an
# independent piece of orchestration state — not bundleable without a
# wrapper object this module doesn't otherwise need.
def run_freq_sweep_at(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    mhz: float,
    mif_path: Path,
    golden_path: Path,
    project_dir: Path,
    build_dir: Path,
) -> dict[str, Any]:
    """Test the board at one candidate clock frequency.

    Edits the project's PLL to mhz (see freq_sweep.set_pll_freq), then
    always does a full recompile+reprogram (quartus_program.
    full_reconfigure) — a clock frequency is baked in at synthesis
    time, so unlike run_one's per-test loop there's no faster
    JTAG-reload path available here — waits
    quartus.program_wait_seconds, dumps RAM, and compares it against
    golden_path.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses freq_sweep.* (see
        freq_sweep.__config__) and quartus.*/memory.ram_base (see
        full_reconfigure_entry/run_one for the quartus.* fields).
    link : JtagLink
        Which JTAG cable/chip to use.
    mhz : float
        Candidate clock frequency to test, in MHz.
    mif_path : Path
        Path to the .mif to bake in as the ROM's init_file for this
        test — the same fixed test program is used at every candidate
        frequency.
    golden_path : Path
        Path to the golden JSON the post-run RAM dump is compared
        against (see mem_validator.compare).
    project_dir : Path
        Path to the Quartus project directory.
    build_dir : Path
        Directory to write this frequency's RAM dump into
        (build_dir/freq_<mhz>mhz_ram.mif).

    Returns
    -------
    dict of {str: Any}
        {"freq_mhz": mhz, "status": status}, status one of "pass",
        "fail" (RAM dump didn't match golden_path),
        "program_fail" (compile or JTAG programming itself failed —
        caught rather than propagated, so one bad candidate frequency
        doesn't abort a whole sweep), or "dump_fail" (the RAM dump
        itself failed after programming succeeded).
    """
    fs_cfg = cfg["freq_sweep"]
    freq_sweep.set_pll_freq(
        pll_file=Path(fs_cfg["pll_file"]),
        mhz=mhz,
        phase_count=fs_cfg["phase_count"],
        freq_param_template=fs_cfg["freq_param_template"],
        phase_param_template=fs_cfg["phase_param_template"],
        freq_unit=fs_cfg["freq_unit"],
        phase_unit=fs_cfg["phase_unit"],
    )

    try:
        quartus_program.full_reconfigure(
            hardware_name=link.hardware_name,
            project_dir=project_dir,
            project_name=cfg["quartus"]["project_name"],
            sof_file=cfg["quartus"]["sof_file"],
            rom_mif_target=cfg["quartus"]["rom_mif_target"],
            stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
            rom_mif_path=mif_path,
        )
    except subprocess.CalledProcessError:
        print(f"{mhz} MHz: compile/program failed")
        return {"freq_mhz": mhz, "status": "program_fail"}

    wait_s = cfg["quartus"]["program_wait_seconds"]
    print(f"Waiting {wait_s}s for the program to run ...")
    time.sleep(wait_s)

    dump_path = build_dir / f"freq_{mhz}mhz_ram.mif"
    try:
        ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], dump_path)
    except subprocess.CalledProcessError:
        print(f"{mhz} MHz: RAM dump failed")
        return {"freq_mhz": mhz, "status": "dump_fail"}

    passed = mem_validator.compare(dump_path, golden_path)
    status = "pass" if passed else "fail"
    print(f"{mhz} MHz: {status.upper()}")
    return {"freq_mhz": mhz, "status": status}


# Same rationale as run_freq_sweep_at above: each arg is independent
# orchestration state.
def run_freq_sweep_linear(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    mif_path: Path,
    golden_path: Path,
    project_dir: Path,
    build_dir: Path,
    start: float,
    stop: float,
    step: float,
) -> list[dict[str, Any]]:
    """Sweep clock frequency linearly from start to stop, in step increments.

    Stops early once _CONSECUTIVE_FAILS_TO_STOP candidates in a row
    fail (see module docstring).

    Parameters
    ----------
    cfg : dict of {str: Any}
        Forwarded to run_freq_sweep_at.
    link : JtagLink
        Which JTAG cable/chip to use.
    mif_path : Path
        Forwarded to run_freq_sweep_at.
    golden_path : Path
        Forwarded to run_freq_sweep_at.
    project_dir : Path
        Forwarded to run_freq_sweep_at.
    build_dir : Path
        Forwarded to run_freq_sweep_at.
    start : float
        First candidate frequency, in MHz.
    stop : float
        Last candidate frequency to try, in MHz (inclusive).
    step : float
        Increment between candidates, in MHz.

    Returns
    -------
    list of dict of {str: Any}
        One run_freq_sweep_at result per candidate frequency actually
        tried, in ascending frequency order.
    """
    results: list[dict[str, Any]] = []
    mhz = start
    while mhz <= stop + 1e-6:
        result = run_freq_sweep_at(
            cfg, link, round(mhz, 3), mif_path, golden_path, project_dir, build_dir
        )
        results.append(result)

        recent = results[-_CONSECUTIVE_FAILS_TO_STOP:]
        if len(results) >= _CONSECUTIVE_FAILS_TO_STOP and all(
            r["status"] != "pass" for r in recent
        ):
            print(
                f"{_CONSECUTIVE_FAILS_TO_STOP} consecutive fails — "
                "stopping sweep early (Fmax likely already found)"
            )
            break

        mhz += step

    return results


# Same rationale as run_freq_sweep_at above: each arg is independent
# orchestration state.
def run_freq_sweep_binary(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    mif_path: Path,
    golden_path: Path,
    project_dir: Path,
    build_dir: Path,
    low: float,
    high: float,
    tolerance: float = 0.5,
) -> list[dict[str, Any]]:
    """Binary-search for Fmax between low (expected PASS) and high (expected FAIL).

    Parameters
    ----------
    cfg : dict of {str: Any}
        Forwarded to run_freq_sweep_at.
    link : JtagLink
        Which JTAG cable/chip to use.
    mif_path : Path
        Forwarded to run_freq_sweep_at.
    golden_path : Path
        Forwarded to run_freq_sweep_at.
    project_dir : Path
        Forwarded to run_freq_sweep_at.
    build_dir : Path
        Forwarded to run_freq_sweep_at.
    low : float
        Lower bound, in MHz — must PASS, or the search aborts (no
        known-good frequency to search from).
    high : float
        Upper bound, in MHz — if this also PASSes, Fmax is above
        `high` and the search can't converge; it returns after
        reporting that rather than guessing further.
    tolerance : float, optional
        Search stops once (hi - lo) <= tolerance, in MHz. Defaults to
        0.5.

    Returns
    -------
    list of dict of {str: Any}
        Every run_freq_sweep_at result tried, in the order tested:
        low bound, high bound, then each successive midpoint.
    """
    results: list[dict[str, Any]] = []

    r = run_freq_sweep_at(cfg, link, low, mif_path, golden_path, project_dir, build_dir)
    results.append(r)
    if r["status"] != "pass":
        print(f"FAIL at lower bound {low} MHz — aborting binary search")
        return results

    r = run_freq_sweep_at(
        cfg, link, high, mif_path, golden_path, project_dir, build_dir
    )
    results.append(r)
    if r["status"] == "pass":
        print(f"PASS at upper bound {high} MHz — Fmax is above {high}, raise --high")
        return results

    lo, hi = low, high
    while (hi - lo) > tolerance:
        mid = round((lo + hi) / 2, 1)
        r = run_freq_sweep_at(
            cfg, link, mid, mif_path, golden_path, project_dir, build_dir
        )
        results.append(r)
        if r["status"] == "pass":
            lo = mid
        else:
            hi = mid

    print(f"Converged: Fmax between {lo} and {hi} MHz")
    return results
