"""Compose the other modules into a full real-hardware test run.

Compiles once (quartus_program), then per test JTAG-writes ROM
(rom_writer) + pulses restart (mailbox) + polls for PASS/FAIL
(mailbox), falling back to a full recompile+reprogram if a test's
mailbox never responds within its timeout (see run_suite/run_one).
The clock frequency sweep, which builds on reconfigure_with_rom, lives
in sweep.py.

Owns no hardware mechanism itself — only sequencing.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools import (
    display,
    mailbox,
    mem_validator,
    quartus_program,
    ram_dump,
    ram_target,
    rom_writer,
)
from riscv_tools.jtag import JtagLink, jtag_chain_healthy


@dataclass(frozen=True)
class RunContext:
    """The orchestration state shared by every test of a suite.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    link : JtagLink
        Which JTAG cable/chip to use.
    build_dir : Path
        Directory the RAM dumps are written into.
    root : Path
        The consuming project's root directory.
    project_dir : Path
        Path to the Quartus project directory.
    """

    cfg: dict[str, Any]
    link: JtagLink
    build_dir: Path
    root: Path
    project_dir: Path


@dataclass(frozen=True)
class SuiteOptions:
    """The optional behaviors of run_suite.

    Parameters
    ----------
    reconfigure : bool, optional
        If True (the default), compile+program the board once before
        running any test. If False, assume the board is ALREADY
        correctly programmed; only use it when you are sure, since a
        wrong guess looks like every test timing out.
    results_path : Path, optional
        If given, write the results here as JSON ({test_name: passed})
        after every single test. None (the default) persists nothing.
    results_so_far : dict of {str: bool}, optional
        Results of an earlier, interrupted invocation covering entries
        NOT in this call's manifest, merged into the returned dict and
        into results_path.
    wait_for_hardware : bool, optional
        If False (the default), a NeedsHumanInterventionError stops
        the suite. If True, block until the JTAG chain is healthy
        again, then retry the step that failed.
    durations : dict of {str: float}, optional
        If given, mutated in place with the wall-clock seconds of each
        test actually run.
    skip_recompile : bool, optional
        Only meaningful when reconfigure is True. If True, the initial
        step is quartus_program.program_only (reprogram the already
        built .sof) instead of a full recompile. Safe only when the
        VHDL source has not changed since that .sof was built.
    """

    reconfigure: bool = True
    results_path: Path | None = None
    results_so_far: dict[str, bool] | None = None
    wait_for_hardware: bool = False
    durations: dict[str, float] | None = None
    skip_recompile: bool = False


class NeedsHumanInterventionError(Exception):
    """A JTAG/hardware failure that no retry can fix.

    It needs a power-cycle.

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
    """Check whether exc matches a known JTAG/cable failure.

    Only the output of exc itself is checked for the signature.

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
    """Load the ROM of entry and pulse the restart flag.

    Then it polls the mailbox.

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
    reconfigure_with_rom(cfg, link, project_dir, root / entry["mif"])


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
        quartus.program_wait_seconds (wait after the tier-3
        reconfigure).
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
        return mailbox.read_configured(link, cfg)
    except subprocess.CalledProcessError as exc:
        _raise_if_hardware_failure(exc)
        print(f"{name}: full recompile+reprogram failed too ({exc})")
        return None


def run_one(
    ctx: RunContext,
    entry: dict[str, Any],
    *,
    position: tuple[int, int] | None = None,
    duration: dict[str, float] | None = None,
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
    ctx : RunContext
        The shared state: the merged project config (see
        run_test_via_jtag and full_reconfigure_entry for the fields
        used, plus quartus.program_wait_seconds), the JTAG link, the
        directory of this test's RAM dump (build_dir/<name>_ram.mif,
        for "memory" tests), the project root (entry["mif"] and
        entry["golden"] are relative to it) and the Quartus project
        directory (used only if the JTAG-reload path times out).
    entry : dict of {str: Any}
        One manifest entry — uses "name", "march", "kind",
        "timeout_s", "mif", and (for "memory" tests) "golden".
    position : tuple of (int, int), keyword-only, optional
        (index, total) — this test's 1-based position in the overall
        suite and the suite's total size, shown in the printed header
        as "[index/total]" (e.g. run_suite's own loop, via
        enumerate(manifest, start=1)). None (the default, e.g. a
        caller running just this one test outside of run_suite) omits
        it from the header instead of printing something misleading
        like "[1/1]".
    duration : dict of {str: float}, keyword-only, optional
        If given, this test's wall-clock time in seconds (JTAG
        reload/poll plus, for "memory" tests, the RAM dump+compare) is
        written into it under entry["name"] as a side effect — the
        caller's own dict, mutated in place, so run_suite's loop can
        report per-test timing back to cli.cmd_run's summary without
        run_suite itself needing a richer return type (results stays a
        plain {name: bool}, unchanged, still what gets persisted to
        results_path/run_progress.json). None (the default) skips
        this, e.g. a caller running just this one test outside of
        run_suite and not interested in the summary version.

    Returns
    -------
    bool
        True if the test passed (mailbox PASS, and the RAM-vs-golden
        compare if applicable), False otherwise.
    """
    name = entry["name"]
    position_prefix = f"[{position[0]}/{position[1]}] " if position else ""
    print(
        f"\n=== {position_prefix}{name} ({entry['march']}, {entry['kind']}, "
        f"timeout={entry['timeout_s']}s) ==="
    )
    start = time.monotonic()

    value = _run_with_recovery(
        ctx.cfg, ctx.link, entry, ctx.root, ctx.project_dir
    )

    if value == mailbox.PASS:
        print(f"{name}: PASS")
        passed = True
    elif value == mailbox.FAIL:
        print(f"{name}: FAIL")
        passed = False
    else:
        print(
            f"{name}: TIMEOUT/UNKNOWN (mailbox={value}); program may not have "
            "finished"
        )
        passed = False

    if entry["kind"] == "memory":
        # Same classification as _run_with_recovery's own tiers: a
        # recognized hardware-failure signature here raises
        # NeedsHumanInterventionError too, same as everywhere else —
        # this was the one JTAG call in run_one that wasn't covered by
        # that logic.
        golden = ctx.root / entry["golden"]
        try:
            dump_path = ctx.build_dir / f"{name}_ram.mif"
            ram_dump.dump_ram(
                ctx.link,
                ram_target.target_from_config(ctx.cfg),
                dump_path,
                mem_validator.golden_word_offsets(golden),
            )
            passed = mem_validator.compare(dump_path, golden) and passed
        except subprocess.CalledProcessError as exc:
            _raise_if_hardware_failure(exc)
            print(
                f"{name}: RAM dump failed ({exc}); can't verify memory content"
            )
            passed = False

    duration_s = time.monotonic() - start
    print(f"{name}: took {duration_s:.1f}s")
    if duration is not None:
        duration[name] = duration_s
    return passed


# How often run_suite's wait_for_hardware mode polls `jtagconfig` while
# blocked waiting for a human to physically fix the board.
_HARDWARE_WAIT_POLL_S = 5.0


def _wait_for_hardware_healthy(
    poll_interval_s: float = _HARDWARE_WAIT_POLL_S,
) -> None:
    """Block until the JTAG chain recovers.

    It polls jtag.jtag_chain_healthy while waiting.

    Meant to be called right after printing a
    NeedsHumanInterventionError's message, only when the caller
    (run_suite's wait_for_hardware=True)
    wants to stay running instead of exiting — the person fixing the
    board (typically a physical power-cycle) is assumed to be watching
    this process's own output, not some separate re-invocation.

    Parameters
    ----------
    poll_interval_s : float, optional
        Seconds between `jtagconfig` checks. Defaults to
        _HARDWARE_WAIT_POLL_S.

    Returns
    -------
    None
        Once jtag_chain_healthy() returns True.
    """
    while not jtag_chain_healthy():
        time.sleep(poll_interval_s)
    print("jtagconfig reports the chain is healthy again — resuming.")


def run_suite(
    ctx: RunContext,
    manifest: list[dict[str, Any]],
    options: SuiteOptions | None = None,
) -> dict[str, bool]:
    """Run every test in manifest against real hardware.

    Compiles and programs the board once, then runs each entry via
    run_one, in order — stopping immediately (not raising) the moment
    any test raises NeedsHumanInterventionError, since no automated
    retry recovers from that (see run_one/_run_with_recovery). If
    options.results_path is given, every test's result is written
    there as soon as it's known — including the stop point itself — so
    a caller can detect an incomplete run (len(returned dict) <
    len(manifest)) and resume later: re-invoke with a caller-filtered
    manifest of just the untested entries (see cli.cmd_run's --resume)
    plus options.results_so_far set to what results_path already held,
    to get a single combined dict back covering the whole original
    manifest across both invocations.

    Parameters
    ----------
    ctx : RunContext
        The shared state, forwarded to full_reconfigure_entry/run_one.
    manifest : list of dict of {str: Any}
        The test list to run (typically compile --emit mif's full
        manifest.json, but may be a caller-filtered subset — see
        cli.cmd_run's --only) — must be non-empty; when
        options.reconfigure is True, manifest[0]'s ROM is what gets
        baked into the initial compile.
    options : SuiteOptions, optional
        The optional behaviors (reconfigure, persistence, resume,
        waiting for the hardware, durations, skip_recompile). None
        (the default) means SuiteOptions().

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
    suite = _SuiteRun(ctx, manifest, options or SuiteOptions())
    if suite.options.reconfigure and not suite.reconfigure():
        return suite.results
    suite.run_entries()
    return suite.results


class _SuiteRun:
    """The state and steps of one run_suite call.

    Parameters
    ----------
    ctx : RunContext
        The shared state.
    manifest : list of dict of {str: Any}
        The non-empty test list.
    options : SuiteOptions
        The optional behaviors.
    """

    def __init__(
        self,
        ctx: RunContext,
        manifest: list[dict[str, Any]],
        options: SuiteOptions,
    ) -> None:
        self.ctx = ctx
        self.manifest = manifest
        self.options = options
        self.already_done = len(options.results_so_far or {})
        self.results: dict[str, bool] = dict(options.results_so_far or {})

    def persist(self) -> None:
        """Write the results so far, if a results path was given."""
        path = self.options.results_path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.results, indent=2))

    def handle_hardware_stop(
        self, name: str, exc: NeedsHumanInterventionError
    ) -> bool:
        """Report a hardware stop.

        Always persists progress and prints exc. If wait_for_hardware,
        blocks in _wait_for_hardware_healthy and returns True (retry
        the step that just failed) instead of False (stop the suite).

        Parameters
        ----------
        name : str
            The test (or step) that hit the failure.
        exc : NeedsHumanInterventionError
            The failure.

        Returns
        -------
        bool
            True if the caller should retry.
        """
        self.persist()
        wait = self.options.wait_for_hardware
        remaining = len(self.manifest) - (
            len(self.results) - self.already_done
        )
        action = (
            "waiting for the board to come back"
            if wait
            else "stopping the suite"
        )
        print(
            f"\n{name}: {action} — {exc}\n"
            f"This needs a physical power-cycle of the board, not "
            f"another retry. {len(self.results)} test(s) done, "
            f"{remaining} remaining (including this one)."
        )
        if not wait:
            print(
                "Once the board is back (`jtagconfig` shows it healthy "
                "again), re-run the exact same command to resume from "
                "here — completed tests won't be re-run."
            )
            return False
        _wait_for_hardware_healthy()
        return True

    def reconfigure(self) -> bool:
        """Compile and program the board once, before any test.

        Returns
        -------
        bool
            False if the suite must stop on a hardware failure.
        """
        print("Compiling and programming the board once ...")
        already_compiled = self.options.skip_recompile
        while True:
            try:
                self._reconfigure_once(already_compiled)
                return True
            except subprocess.CalledProcessError as exc:
                already_compiled = True
                if not self._can_retry(exc):
                    return False

    def _reconfigure_once(self, already_compiled: bool) -> None:
        """Run one attempt of the initial reconfigure.

        A previous attempt that already got quartus_sh --flow compile
        to succeed leaves a known-good .sof, because the signatures
        _raise_if_hardware_failure matches are all quartus_pgm/
        quartus_stp text, never emitted unless the compile finished.
        Then only the reprogramming needs retrying, not another
        several-minute recompile of an identical design.

        Parameters
        ----------
        already_compiled : bool
            Whether to reprogram the existing .sof only.
        """
        ctx = self.ctx
        if already_compiled:
            quartus_program.program_only(
                hardware_name=ctx.link.hardware_name,
                project_dir=ctx.project_dir,
                sof_file=ctx.cfg["quartus"]["sof_file"],
            )
        else:
            full_reconfigure_entry(
                ctx.cfg,
                ctx.link,
                self.manifest[0],
                ctx.root,
                ctx.project_dir,
            )

    def _can_retry(self, exc: subprocess.CalledProcessError) -> bool:
        """Classify a failure of the initial reconfigure.

        Unlike run_one's own tiers, there's no retry path for the
        initial reconfigure itself: either this is a known JTAG/cable
        signature (handled like every other call site) or it's a real
        build/hardware problem, which still propagates as a hard
        failure.

        Parameters
        ----------
        exc : subprocess.CalledProcessError
            The failure.

        Returns
        -------
        bool
            True to retry, False to stop the suite.

        Raises
        ------
        subprocess.CalledProcessError
            exc itself, when it is not a known hardware failure.
        """
        try:
            _raise_if_hardware_failure(exc)
        except NeedsHumanInterventionError as hi_exc:
            return self.handle_hardware_stop(self.manifest[0]["name"], hi_exc)
        raise exc

    def run_entries(self) -> None:
        """Run every manifest entry, stopping on a hardware failure."""
        # 1-based position across the ORIGINAL manifest, not just this
        # invocation's (possibly resumed/already-filtered) one — a
        # resume restarting the header count at "[1/N]" would
        # understate both how far along the suite actually is and what
        # N even means.
        total = self.already_done + len(self.manifest)
        show = bool(
            self.ctx.cfg.get("orchestrator", {}).get("board_display", False)
        )
        if show and not self.already_done:
            # a new session starts without a failure; a resumed one
            # keeps the flag it had
            display.write_fail(self.ctx.link, False)
        for i, entry in enumerate(self.manifest, start=self.already_done + 1):
            if show:
                # the number of the program in the session, in
                # decimal, on the six digits
                display.write_display(self.ctx.link, display.encode_test(i))
            if not self._run_entry(entry, (i, total), show):
                return
            self.persist()

    def _run_entry(
        self, entry: dict[str, Any], position: tuple[int, int], show: bool
    ) -> bool:
        """Run one entry, retrying after a hardware stop if asked.

        Parameters
        ----------
        entry : dict of {str: Any}
            The manifest entry.
        position : tuple of (int, int)
            (index, total) of the entry in the whole suite.
        show : bool
            Whether the board display follows the suite.

        Returns
        -------
        bool
            False if the suite must stop.
        """
        name = entry["name"]
        while True:
            try:
                passed = run_one(
                    self.ctx,
                    entry,
                    position=position,
                    duration=self.options.durations,
                )
            except NeedsHumanInterventionError as exc:
                if self.handle_hardware_stop(name, exc):
                    continue
                return False
            self.results[name] = passed
            if show and not passed:
                # the first red LED stays lit once any program has
                # failed
                display.write_fail(self.ctx.link, True)
            return True
