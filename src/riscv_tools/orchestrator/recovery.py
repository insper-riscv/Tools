"""Escalate through the recovery tiers when a test times out."""

import subprocess
import time
from pathlib import Path
from typing import Any

from riscv_tools import (
    mailbox,
    quartus_program,
)
from riscv_tools.jtag import JtagLink
from riscv_tools.orchestrator.failure import raise_if_hardware_failure
from riscv_tools.orchestrator.jtag_run import (
    full_reconfigure_entry,
    run_test_via_jtag,
)


def run_with_recovery(
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
