"""Run the real-hardware test suite.

Compiles once, then for each test writes the ROM over JTAG, pulses the
restart and polls the PASS/FAIL mailbox. If a test's mailbox never
responds within its timeout, it falls back to a full recompile and
reprogram. The clock frequency sweep is in sweep.py.
"""

import subprocess
import time
from typing import Any

from riscv_tools import (
    mailbox,
    mem_validator,
    ram_dump,
    ram_target,
)
from riscv_tools.orchestrator.context import RunContext
from riscv_tools.orchestrator.failure import raise_if_hardware_failure
from riscv_tools.orchestrator.recovery import run_with_recovery


def run_one(
    ctx: RunContext,
    entry: dict[str, Any],
    *,
    position: tuple[int, int] | None = None,
    duration: dict[str, float] | None = None,
) -> bool:
    """Run a single test end to end.

    Reloads the ROM over JTAG and polls the mailbox, escalating through
    the recovery tiers of run_with_recovery on timeout, then compares
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

    value = run_with_recovery(
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
