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

import json
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


class NeedsHumanInterventionError(Exception):
    """A JTAG/hardware failure that no automated retry can fix — needs a power-cycle.

    Raised by _run_with_recovery when a subprocess failure's own error
    text matches a known "the board/cable itself is unreachable"
    signature (see _is_hardware_failure), as opposed to an ordinary
    test timeout (mailbox never went PASS/FAIL, but every JTAG
    operation involved reported success) — that second case might be a
    real CPU/test bug, not a wedged board, and doesn't raise this.

    run_suite catches this, saves progress, and stops the suite rather
    than ever calling run_one on the next manifest entry — no automated
    retry has ever recovered from one of these this session (0/7 full
    recompiles), so there is nothing left to try except a human
    physically power-cycling the board.
    """


# Substrings pulled directly from real Quartus/jtagd error text seen
# this session (see docs/PLL_LOCK_LOSS_BUG.md and
# HARDWARE_PROGRAMMING.md) that mean "the JTAG chain/cable itself is
# unreachable" — never "the design misbehaved" or "the test failed".
# Matched case-insensitively against a CalledProcessError's stdout+
# stderr (see jtag.link.run / quartus_program._run_captured — both
# always populate these now, specifically so this classifier has
# something to look at).
_HARDWARE_FAILURE_SIGNATURES = (
    "can't scan jtag chain",
    "jtag chain broken",
    "unable to read device chain",
    "programming hardware cable not detected",
    "hardware is not found",
    "no editable memory instance",
    "error when scanning hardware",
)


def _is_hardware_failure(exc: subprocess.CalledProcessError) -> bool:
    """Check whether exc's own output matches a known JTAG/cable failure signature.

    Parameters
    ----------
    exc : subprocess.CalledProcessError
        A failure from jtag.link.run/run_tcl or
        quartus_program._run_captured — both always populate
        .stdout/.stderr with real text now (see their own docstrings).

    Returns
    -------
    bool
        True if exc's stdout+stderr contain one of
        _HARDWARE_FAILURE_SIGNATURES — this specific test's own retry
        tiers are exhausted, and neither would a trying-again-later
        retry help without a human power-cycling the board first.
        False for any other failure (e.g. a nonzero exit with
        different or no output) — treated as an ordinary test failure,
        not grounds to stop the whole suite.
    """
    text = f"{exc.stdout or ''}\n{exc.stderr or ''}".lower()
    return any(sig in text for sig in _HARDWARE_FAILURE_SIGNATURES)


def _raise_if_hardware_failure(exc: subprocess.CalledProcessError) -> None:
    """Re-raise exc as NeedsHumanInterventionError if it looks like one.

    No-op otherwise.

    Pulled out of _run_with_recovery's own tiers (repeated once per
    tier) purely to keep that function's branch count down — the
    actual classification logic lives in _is_hardware_failure.
    """
    if _is_hardware_failure(exc):
        raise NeedsHumanInterventionError(str(exc)) from exc


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
        quartus.rom_mem_instances/ram_mem_instance/
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
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instances"], root / entry["mif"])
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
def _run_with_recovery(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> int | None:
    """Run entry via JTAG, escalating through recovery tiers on timeout.

    Three tiers, each tried only if the previous one didn't get a
    mailbox result either:

    1. A cheap soft restart (re-reload ROM + re-pulse go_flag, no JTAG
       programming) — crt0.S's _start unconditionally clears
       mailbox_addr/go_flag_addr itself before running anything, so
       this gives the core a real chance to leave whatever state it
       was stuck in (its own poll loop, most likely).
    2. A plain reprogram (existing .sof, no recompile) — ~10s instead
       of the several minutes a full compile takes. The design never
       changes between tests in this same-frequency suite (only the
       ROM content, reloaded over JTAG separately), so recompiling
       would produce the identical bitstream.
    3. A full recompile + reprogram — but ONLY if tier 2 failed because
       the .sof itself doesn't exist (FileNotFoundError), not because
       quartus_pgm couldn't reach the board. Recompiling can't fix a
       JTAG chain that's down (that needs a physical power-cycle
       either way) and produces the identical bitstream tier 2 already
       tried — empirically 0/7 of those recompiles recovered a single
       test this session, at ~4-5 minutes each. Skipping this tier
       when it can't help is the whole point of separating it from
       tier 2's failure handling.

    Raises NeedsHumanInterventionError as soon as any tier's own failure
    text matches a known hardware/cable signature (see
    _is_hardware_failure) — no automated tier below has ever recovered
    from one of those this session, so there's no point paying for
    tier 2/3 just to confirm it again more expensively. A tier that
    fails with unrecognized output (or a plain timeout with no
    subprocess error at all) is NOT escalated this way — that might be
    a real CPU/test bug rather than a wedged board, and still gets to
    try the next, cheaper tier before this function gives up and
    returns None.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — see run_test_via_jtag and
        full_reconfigure_entry for the fields used, plus
        quartus.program_wait_seconds (wait after the tier-3 reconfigure).
    link : JtagLink
        Which JTAG cable/chip to use.
    entry : dict of {str: Any}
        One manifest entry — uses "name", "march", "kind", "timeout_s",
        "mif" (see run_test_via_jtag/full_reconfigure_entry).
    root : Path
        The consuming project's root directory, entry["mif"] is
        relative to this.
    project_dir : Path
        Path to the Quartus project directory, used only by tiers 2/3.

    Returns
    -------
    int or None
        The mailbox value (mailbox.PASS or mailbox.FAIL), or None if
        every tier failed to get one without ever hitting a
        recognized hardware-failure signature.

    Raises
    ------
    NeedsHumanInterventionError
        A tier's own subprocess failure matched a known JTAG/cable
        signature — see _is_hardware_failure.
    """
    name = entry["name"]

    try:
        value = run_test_via_jtag(cfg, link, entry, root)
    except subprocess.CalledProcessError as exc:
        # A JTAG chain that's already down when this test starts (e.g.
        # the previous test's own fallback never got the board back)
        # fails write_rom/pulse_go_flag immediately, before any
        # polling even begins.
        _raise_if_hardware_failure(exc)
        value = None

    if value is not None:
        return value

    # Tier 1: cheap soft restart. Matters because a tier-3 recompile
    # leaves the core running UNSUPERVISED for however long `quartus_sh
    # --flow compile` takes (minutes) before quartus_pgm ever touches
    # the cable again — that's a long window for a spinning core to
    # make things worse, not better, before we even attempt the
    # expensive/fragile path.
    print(
        f"{name}: no mailbox result after {entry['timeout_s']}s; "
        "retrying a soft restart (rewrite ROM + pulse go-flag) once "
        "before trying a plain reprogram"
    )
    try:
        value = run_test_via_jtag(cfg, link, entry, root)
    except subprocess.CalledProcessError as exc:
        _raise_if_hardware_failure(exc)
        value = None

    if value is not None:
        return value

    # Tier 2: plain reprogram, no recompile. FileNotFoundError means
    # "no .sof to reprogram from at all" (tier 3 can actually help,
    # unrelated to the board's JTAG reachability) — distinct from a
    # CalledProcessError, which means quartus_pgm itself ran and either
    # hit a recognized hardware failure (raise, stop the suite) or
    # something else entirely (fall through, still worth a timeout
    # report rather than assuming the board is wedged).
    print(
        f"{name}: still no mailbox result after a soft restart; "
        "trying a plain reprogram (existing .sof, no recompile)"
    )
    sof_missing = False
    try:
        quartus_program.program_only(
            hardware_name=link.hardware_name,
            project_dir=project_dir,
            sof_file=cfg["quartus"]["sof_file"],
        )
        value = run_test_via_jtag(cfg, link, entry, root)
    except FileNotFoundError:
        value = None
        sof_missing = True
    except subprocess.CalledProcessError as exc:
        _raise_if_hardware_failure(exc)
        value = None

    if value is not None:
        return value

    if not sof_missing:
        print(
            f"{name}: still no mailbox result after a plain reprogram, "
            "with no recognized hardware-failure signature in any "
            "output so far — reporting this as a timeout rather than "
            "assuming the board is wedged (a full recompile would just "
            "reprogram the identical bitstream anyway)."
        )
        return None

    # Tier 3: full recompile + reprogram — only reached when there's no
    # .sof to fall back on.
    print(
        f"{name}: still no mailbox result, and no .sof exists to "
        "reprogram from — falling back to a full recompile+reprogram, "
        "which this specific case actually needs"
    )
    try:
        full_reconfigure_entry(cfg, link, entry, root, project_dir)
        wait_s = cfg["quartus"]["program_wait_seconds"]
        print(f"Waiting {wait_s}s for the program to run ...")
        time.sleep(wait_s)
        return mailbox.read_mailbox(
            link,
            cfg["quartus"]["ram_mem_instance"],
            cfg["memory"]["ram_base"],
            cfg["memory"]["mailbox_addr"],
        )
    except subprocess.CalledProcessError as exc:
        _raise_if_hardware_failure(exc)
        print(f"{name}: full recompile+reprogram failed too ({exc})")
        return None


def run_one(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    build_dir: Path,
    root: Path,
    project_dir: Path,
) -> bool:
    """Run a single test end to end.

    JTAG-reload + poll with recovery-tier escalation on timeout (see
    _run_with_recovery for the full tier breakdown), then a
    RAM-vs-golden compare if entry is a "memory" test. Raises
    NeedsHumanInterventionError (RAM dump included) the moment any JTAG
    operation's own failure text matches a known hardware/cable
    signature — see _is_hardware_failure — since no automated retry
    has ever recovered from one of those; run_suite catches it, saves
    progress, and stops rather than grinding through the rest of the
    manifest against a board that needs a human to power-cycle it.
    Anything else (a plain timeout, or a subprocess failure with
    unrecognized output) comes back as a plain False instead.

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

    value = _run_with_recovery(cfg, link, entry, root, project_dir)

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
        # Same classification as _run_with_recovery's own tiers: a
        # recognized hardware-failure signature here raises
        # NeedsHumanInterventionError too, same as everywhere else — this
        # was the one JTAG call in run_one that wasn't covered by that
        # logic.
        try:
            dump_path = build_dir / f"{name}_ram.mif"
            ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], dump_path)
            passed = mem_validator.compare(dump_path, root / entry["golden"]) and passed
        except subprocess.CalledProcessError as exc:
            _raise_if_hardware_failure(exc)
            print(f"{name}: RAM dump failed ({exc}); can't verify memory content")
            passed = False

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
    results_path: Path | None = None,
    results_so_far: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Run every test in manifest against real hardware.

    Compiles and programs the board once, then runs each entry via
    run_one, in order — stopping immediately (not raising) the moment
    any test raises NeedsHumanInterventionError, since no automated retry
    recovers from that (see run_one/_run_with_recovery). If
    results_path is given, every test's result is written there as
    soon as it's known — including the stop point itself — so a
    caller can detect an incomplete run (len(returned dict) <
    len(manifest)) and resume later: re-invoke with a
    caller-filtered manifest of just the untested entries (see
    cli.cmd_run's --resume) plus results_so_far set to what
    results_path already held, to get a single combined dict back
    covering the whole original manifest across both invocations.

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
    results_path : Path, optional
        If given, write results here as JSON ({test_name: passed})
        after every single test — not just at the end — so progress
        survives a NeedsHumanInterventionError stop (or, for that matter, a
        crash/kill of this process itself). None (the default) means
        don't persist anything.
    results_so_far : dict of {str: bool}, optional
        Results from an earlier, interrupted invocation covering
        entries NOT in this call's manifest — merged into both the
        returned dict and whatever gets written to results_path, so
        callers resuming a stopped run get one complete picture back
        instead of having to merge dicts themselves. None (the
        default) is equivalent to an empty dict.

    Returns
    -------
    dict of {str: bool}
        A {test_name: passed} dict — results_so_far, plus one entry
        per manifest test actually run before either finishing or
        hitting a NeedsHumanInterventionError stop. Compare len(this)
        against len(results_so_far or {}) + len(manifest) to tell a
        full run from a stopped one.

    Raises
    ------
    ValueError
        manifest is empty.
    """
    if not manifest:
        raise ValueError("Manifest is empty; nothing to run")

    results: dict[str, bool] = dict(results_so_far or {})

    def _persist() -> None:
        if results_path is not None:
            results_path.parent.mkdir(parents=True, exist_ok=True)
            results_path.write_text(json.dumps(results, indent=2))

    def _stop_for_hi(name: str, exc: NeedsHumanInterventionError) -> dict[str, bool]:
        _persist()
        already_done = len(results_so_far or {})
        remaining = len(manifest) - (len(results) - already_done)
        print(
            f"\n{name}: stopping the suite — {exc}\n"
            f"This needs a physical power-cycle of the board, not "
            f"another retry. {len(results)} test(s) done, {remaining} "
            f"remaining (including this one). Once the board is back "
            f"(`jtagconfig` shows it healthy again), re-run the exact "
            f"same command to resume from here — completed tests "
            f"won't be re-run."
        )
        return results

    if reconfigure:
        print("Compiling and programming the board once ...")
        try:
            full_reconfigure_entry(cfg, link, manifest[0], root, project_dir)
        except subprocess.CalledProcessError as exc:
            # Unlike run_one's own tiers, there's no retry path for the
            # initial reconfigure itself — either this is a known
            # JTAG/cable signature (stop the suite gracefully, same as
            # every other call site) or it's a real build/hardware
            # problem, which should still propagate as a hard failure.
            try:
                _raise_if_hardware_failure(exc)
            except NeedsHumanInterventionError as hi_exc:
                return _stop_for_hi(manifest[0]["name"], hi_exc)
            raise

    for entry in manifest:
        try:
            results[entry["name"]] = run_one(
                cfg, link, entry, build_dir, root, project_dir
            )
        except NeedsHumanInterventionError as exc:
            return _stop_for_hi(entry["name"], exc)
        _persist()

    return results


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
