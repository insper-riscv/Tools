"""Run the real-hardware test suite.

Compiles once, then for each test writes the ROM over JTAG, pulses the
restart and polls the PASS/FAIL mailbox. If a test's mailbox never
responds within its timeout, it falls back to a full recompile and
reprogram. The clock frequency sweep is in sweep.py.
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools import (
    mailbox,
    mem_validator,
    quartus_program,
    ram_dump,
    ram_target,
    rom_writer,
)
from riscv_tools.jtag import JtagLink
from riscv_tools.orchestrator.failure import raise_if_hardware_failure


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


def _run_with_recovery(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> int | None:
    """Run entry via JTAG, escalating through recovery tiers on timeout.

    Each tier is tried only if the previous one got no mailbox result:

    1. A soft restart: reload the ROM and pulse the go flag again.
    2. A plain reprogram from the existing .sof, about 10 s instead of
       the minutes a full compile takes; the design never changes
       between tests, so recompiling would give the same bitstream.
    3. A full recompile and reprogram, only if tier 2 failed because the
       .sof does not exist (FileNotFoundError); recompiling cannot fix a
       JTAG chain that is down.

    Raises NeedsHumanInterventionError as soon as a tier's failure text
    matches a known hardware or cable signature (see
    _is_hardware_failure), since no automated tier recovers from one.
    Any other failure, or a timeout with no subprocess error, goes on to
    the next tier; when all fail, it returns None.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; see run_test_via_jtag and
        full_reconfigure_entry for the fields used, plus
        quartus.program_wait_seconds (wait after the tier-3
        reconfigure).
    link : JtagLink
        Which JTAG cable/chip to use.
    entry : dict of {str: Any}
        One manifest entry: uses "name", "march", "kind", "timeout_s",
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
        signature; see _is_hardware_failure.
    """
    name = entry["name"]

    # A JTAG chain that's already down when this test starts (for
    # example because the previous test's fallback never got the board
    # back) fails right away, before any polling begins.
    value = _try_jtag(cfg, link, entry, root)
    if value is not None:
        return value

    # Tier 1: cheap soft restart. A tier-3 recompile leaves the core
    # running unsupervised while `quartus_sh --flow compile` takes
    # minutes, which can make things worse before the expensive path
    # is even tried.
    print(
        f"{name}: no mailbox result after {entry['timeout_s']}s; "
        "retrying a soft restart (rewrite ROM + pulse go-flag) once "
        "before trying a plain reprogram"
    )
    value = _try_jtag(cfg, link, entry, root)
    if value is not None:
        return value

    # Tier 2: plain reprogram, no recompile.
    print(
        f"{name}: still no mailbox result after a soft restart; "
        "trying a plain reprogram (existing .sof, no recompile)"
    )
    value, sof_missing = _try_reprogram(cfg, link, entry, root, project_dir)
    if value is not None:
        return value

    if not sof_missing:
        print(
            f"{name}: still no mailbox result after a plain reprogram, "
            "with no recognized hardware-failure signature in any "
            "output so far, reporting this as a timeout rather than "
            "assuming the board is wedged (a full recompile would just "
            "reprogram the identical bitstream anyway)."
        )
        return None

    # Tier 3: full recompile + reprogram, only when there is no .sof.
    print(
        f"{name}: still no mailbox result, and no .sof exists to "
        "reprogram from, falling back to a full recompile+reprogram, "
        "which this specific case actually needs"
    )
    return _try_recompile(cfg, link, entry, root, project_dir)


def _try_jtag(
    cfg: dict[str, Any], link: JtagLink, entry: dict[str, Any], root: Path
) -> int | None:
    """Run entry via JTAG once.

    Returns
    -------
    int or None
        The mailbox value, or None if the test never answered.

    Raises
    ------
    NeedsHumanInterventionError
        The failure matches a known hardware or cable signature.
    """
    try:
        return run_test_via_jtag(cfg, link, entry, root)
    except subprocess.CalledProcessError as exc:
        raise_if_hardware_failure(exc)
        return None


def _try_reprogram(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> tuple[int | None, bool]:
    """Reprogram from the existing .sof (tier 2), then run entry.

    A missing .sof means tier 3 can help; a failed quartus_pgm that is
    not a known hardware failure is an ordinary timeout.

    Returns
    -------
    tuple of (int or None, bool)
        The mailbox value, and whether the .sof was missing.

    Raises
    ------
    NeedsHumanInterventionError
        The failure matches a known hardware or cable signature.
    """
    try:
        quartus_program.program_only(
            hardware_name=link.hardware_name,
            project_dir=project_dir,
            sof_file=cfg["quartus"]["sof_file"],
        )
        return run_test_via_jtag(cfg, link, entry, root), False
    except FileNotFoundError:
        return None, True
    except subprocess.CalledProcessError as exc:
        raise_if_hardware_failure(exc)
        return None, False


def _try_recompile(
    cfg: dict[str, Any],
    link: JtagLink,
    entry: dict[str, Any],
    root: Path,
    project_dir: Path,
) -> int | None:
    """Recompile, reprogram and run entry (tier 3).

    Returns
    -------
    int or None
        The mailbox value, or None if the recompile failed.

    Raises
    ------
    NeedsHumanInterventionError
        The failure matches a known hardware or cable signature.
    """
    try:
        full_reconfigure_entry(cfg, link, entry, root, project_dir)
        wait_s = cfg["quartus"]["program_wait_seconds"]
        print(f"Waiting {wait_s}s for the program to run ...")
        time.sleep(wait_s)
        return mailbox.read_configured(link, cfg)
    except subprocess.CalledProcessError as exc:
        raise_if_hardware_failure(exc)
        print(f"{entry['name']}: full recompile+reprogram failed too ({exc})")
        return None


def run_one(
    ctx: RunContext,
    entry: dict[str, Any],
    *,
    position: tuple[int, int] | None = None,
    duration: dict[str, float] | None = None,
) -> bool:
    """Run a single test end to end.

    Reloads the ROM over JTAG and polls the mailbox, escalating through
    the recovery tiers of _run_with_recovery on timeout, then compares
    RAM with the golden for a "memory" test. Raises
    NeedsHumanInterventionError (RAM dump included) as soon as a JTAG
    failure matches a known hardware signature; run_suite catches it and
    stops. Anything else (a timeout, or a subprocess failure with
    unrecognized output) comes back as a plain False.

    Parameters
    ----------
    ctx : RunContext
        The shared state: the merged project config, the JTAG link, the
        directory of this test's RAM dump, the project root and the
        Quartus project directory.
    entry : dict of {str: Any}
        One manifest entry: uses "name", "march", "kind",
        "timeout_s", "mif", and (for "memory" tests) "golden".
    position : tuple of (int, int), keyword-only, optional
        (index, total) of this test in the suite, shown as
        "[index/total]" in the printed header. None (the default) omits
        it.
    duration : dict of {str: float}, keyword-only, optional
        If given, receives this test's wall-clock time in seconds under
        entry["name"]. None (the default) skips it.

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

    passed = _report_verdict(name, value)
    if entry["kind"] == "memory":
        passed = _check_ram(ctx, entry) and passed

    duration_s = time.monotonic() - start
    print(f"{name}: took {duration_s:.1f}s")
    if duration is not None:
        duration[name] = duration_s
    return passed


def _report_verdict(name: str, value: int | None) -> bool:
    """Print the verdict of a test and return whether it passed."""
    if value == mailbox.PASS:
        print(f"{name}: PASS")
        return True
    if value == mailbox.FAIL:
        print(f"{name}: FAIL")
        return False
    print(
        f"{name}: TIMEOUT/UNKNOWN (mailbox={value}); program may not have "
        "finished"
    )
    return False


def _check_ram(ctx: RunContext, entry: dict[str, Any]) -> bool:
    """Dump the RAM and compare it with the golden of a "memory" test.

    Raises
    ------
    NeedsHumanInterventionError
        The dump failed with a known hardware or cable signature.
    """
    name = entry["name"]
    golden = ctx.root / entry["golden"]
    try:
        dump_path = ctx.build_dir / f"{name}_ram.mif"
        ram_dump.dump_ram(
            ctx.link,
            ram_target.target_from_config(ctx.cfg),
            dump_path,
            mem_validator.golden_word_offsets(golden),
        )
        return mem_validator.compare(dump_path, golden)
    except subprocess.CalledProcessError as exc:
        raise_if_hardware_failure(exc)
        print(f"{name}: RAM dump failed ({exc}); can't verify memory content")
        return False
