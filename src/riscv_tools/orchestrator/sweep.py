"""The clock frequency sweep: a PLL edit and a reconfigure per step.

Edits the project's PLL (freq_sweep) and does a full
recompile+reprogram+RAM-compare at each candidate frequency, since a
clock frequency is baked in at synthesis time (see run_freq_sweep_linear
and run_freq_sweep_binary).
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools import (
    freq_sweep,
    htif,
    mem_validator,
    ram_dump,
    ram_target,
)
from riscv_tools.jtag import JtagLink
from riscv_tools.orchestrator.jtag_run import reconfigure_with_rom

# run_freq_sweep_linear stops once this many consecutive candidates
# fail; past that point the board is assumed to already be beyond
# Fmax, so continuing just burns more full-reconfigure cycles for no
# new information.
_CONSECUTIVE_FAILS_TO_STOP = 3


@dataclass(frozen=True)
class SweepJob:
    """What a clock frequency sweep needs besides the frequencies.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config, using freq_sweep.*, quartus.* and
        memory.ram_base.
    link : JtagLink
        Which JTAG cable/chip to use.
    mif_path : Path
        The .mif to bake in as the ROM's init_file at every candidate
        frequency: the same fixed test program is used each time.
    golden_path : Path
        The golden JSON the post-run RAM dump is compared against.
    project_dir : Path
        Path to the Quartus project directory.
    build_dir : Path
        Directory the RAM dump of each frequency is written into.
    """

    cfg: dict[str, Any]
    link: JtagLink
    mif_path: Path
    golden_path: Path
    project_dir: Path
    build_dir: Path


def run_freq_sweep_at(job: SweepJob, mhz: float) -> dict[str, Any]:
    """Test the board at one candidate clock frequency.

    Edits the project's PLL to mhz, then always does a full recompile
    and reprogram, since the frequency is baked in at synthesis time. It
    waits quartus.program_wait_seconds, reads tohost, dumps RAM and
    compares it with job.golden_path. The frequency passes only if the
    program signaled a pass in tohost and the RAM matches.

    Parameters
    ----------
    job : SweepJob
        The sweep's shared state: the merged project config, the JTAG
        link, the .mif to bake in, the golden JSON the RAM dump is
        compared with, the Quartus project directory and the RAM dump
        directory.
    mhz : float
        Candidate clock frequency to test, in MHz.

    Returns
    -------
    dict of {str: Any}
        {"freq_mhz": mhz, "status": status}, status one of "pass",
        "hang" (tohost never signaled completion),
        "fail" (tohost signaled a failure, or the RAM dump didn't match
        golden_path),
        "program_fail" (compile or JTAG programming itself failed,
        caught rather than propagated, so one bad candidate frequency
        doesn't abort a whole sweep), or "dump_fail" (the tohost read
        or the RAM dump failed after programming succeeded).
    """
    cfg = job.cfg
    link = job.link
    fs_cfg = cfg["freq_sweep"]
    freq_sweep.set_pll_freq(
        pll_file=Path(fs_cfg["pll_file"]),
        mhz=mhz,
        params=freq_sweep.PllParams(
            phase_count=fs_cfg["phase_count"],
            freq_param_template=fs_cfg["freq_param_template"],
            phase_param_template=fs_cfg["phase_param_template"],
            freq_unit=fs_cfg["freq_unit"],
            phase_unit=fs_cfg["phase_unit"],
        ),
    )

    try:
        reconfigure_with_rom(cfg, link, job.project_dir, job.mif_path)
    except subprocess.CalledProcessError:
        print(f"{mhz} MHz: compile/program failed")
        return {"freq_mhz": mhz, "status": "program_fail"}

    wait_s = cfg["quartus"]["program_wait_seconds"]
    print(f"Waiting {wait_s}s for the program to run ...")
    time.sleep(wait_s)

    dump_path = job.build_dir / f"freq_{mhz}mhz_ram.mif"
    try:
        tohost = htif.read_tohost_configured(link, cfg)
        ram_dump.dump_ram(
            link,
            ram_target.target_from_config(cfg),
            dump_path,
            mem_validator.golden_word_offsets(job.golden_path),
        )
    except subprocess.CalledProcessError:
        print(f"{mhz} MHz: tohost read or RAM dump failed")
        return {"freq_mhz": mhz, "status": "dump_fail"}

    if not htif.is_done(tohost):
        status = "hang"
    elif tohost == htif.PASS and mem_validator.compare(
        dump_path, job.golden_path
    ):
        status = "pass"
    else:
        status = "fail"
    print(f"{mhz} MHz: {status.upper()}")
    return {"freq_mhz": mhz, "status": status}


def run_freq_sweep_linear(
    job: SweepJob,
    start: float,
    stop: float,
    step: float,
) -> list[dict[str, Any]]:
    """Sweep the clock frequency linearly from start to stop.

    The sweep goes in step increments.

    Stops early once _CONSECUTIVE_FAILS_TO_STOP candidates in a row
    fail (see module docstring).

    Parameters
    ----------
    job : SweepJob
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
        result = run_freq_sweep_at(job, round(mhz, 3))
        results.append(result)

        recent = results[-_CONSECUTIVE_FAILS_TO_STOP:]
        if len(results) >= _CONSECUTIVE_FAILS_TO_STOP and all(
            r["status"] != "pass" for r in recent
        ):
            print(
                f"{_CONSECUTIVE_FAILS_TO_STOP} consecutive fails; "
                "stopping sweep early (Fmax likely already found)"
            )
            break

        mhz += step

    return results


def run_freq_sweep_binary(
    job: SweepJob,
    low: float,
    high: float,
    tolerance: float = 0.5,
) -> list[dict[str, Any]]:
    """Binary-search for Fmax between low and high.

    The low end is expected to PASS and the high end to FAIL.

    Parameters
    ----------
    job : SweepJob
        Forwarded to run_freq_sweep_at.
    low : float
        Lower bound, in MHz: must PASS, or the search aborts (no
        known-good frequency to search from).
    high : float
        Upper bound, in MHz: if this also PASSes, Fmax is above
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

    r = run_freq_sweep_at(job, low)
    results.append(r)
    if r["status"] != "pass":
        print(f"FAIL at lower bound {low} MHz; aborting binary search")
        return results

    r = run_freq_sweep_at(job, high)
    results.append(r)
    if r["status"] == "pass":
        print(
            f"PASS at upper bound {high} MHz; Fmax is above {high}, raise "
            "--high"
        )
        return results

    lo, hi = low, high
    while (hi - lo) > tolerance:
        mid = round((lo + hi) / 2, 1)
        r = run_freq_sweep_at(job, mid)
        results.append(r)
        if r["status"] == "pass":
            lo = mid
        else:
            hi = mid

    print(f"Converged: Fmax between {lo} and {hi} MHz")
    return results
