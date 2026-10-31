"""Run a compiled test's ELF to completion under Spike.

The test signals its verdict through HTIF: crt0.S in the consuming
project writes 1 to tohost for a pass and 3 for a fail. Spike exits
with that value shifted right by one, so 0 is a pass and any other
status is a fail. No hardware is involved, which makes this a fast
software check to run before a real-hardware or simulation suite.
"""

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from riscv_tools.spike_exec import (
    SpikeTarget,
    prepared_elf,
    require_spike,
    run_spike,
    spike_command,
    symbol_address,
)


@dataclass(frozen=True)
class SpikeRunResult:
    """Outcome of one Spike run.

    Attributes
    ----------
    passed : bool
        True when Spike exited with status 0 before the timeout.
    exit_code : int or None
        Spike's exit status, or None when the run timed out.
    output : str
        Everything Spike printed (stdout then stderr), including its
        own `*** FAILED ***` line for a failing test.
    """

    passed: bool
    exit_code: int | None
    output: str


def run_elf(
    target: SpikeTarget,
    elf_path: Path,
    timeout_s: float = 60.0,
) -> SpikeRunResult:
    """Run elf_path under Spike until it writes tohost or times out.

    Parameters
    ----------
    target : SpikeTarget
        The Spike run settings: binaries, ISA, memory regions and the
        tohost and entry symbols.
    elf_path : Path
        Compiled test ELF to run.
    timeout_s : float, optional
        Seconds to wait before declaring the test hung.

    Returns
    -------
    SpikeRunResult
        The verdict and Spike's output.

    Raises
    ------
    RuntimeError
        The entry or tohost symbol isn't in the ELF.
    """
    spike = replace(target, spike_bin=require_spike(target.spike_bin))
    entry_pc = symbol_address(spike.nm_bin, elf_path, spike.entry_symbol)
    with prepared_elf(
        spike.objcopy_bin, spike.nm_bin, elf_path, spike.tohost_symbol
    ) as elf:
        cmd = spike_command(spike, entry_pc, elf)
        try:
            proc = run_spike(cmd, timeout_s)
        except subprocess.TimeoutExpired:
            return SpikeRunResult(False, None, f"timed out after {timeout_s}s")
    return SpikeRunResult(
        proc.returncode == 0, proc.returncode, proc.stdout + proc.stderr
    )
