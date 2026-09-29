"""Run a compiled test's ELF to completion under Spike.

The test signals its verdict through HTIF: crt0.S in the consuming
project writes 1 to tohost for a pass and 3 for a fail. Spike exits
with that value shifted right by one, so 0 is a pass and any other
status is a fail. No hardware is involved, which makes this a fast
software check to run before a real-hardware or simulation suite.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.spike_exec import (
    prepared_elf,
    require_spike,
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


# Each arg is an independent Spike run setting; not bundleable
# without a config object this module doesn't otherwise need.
def run_elf(  # noqa: PLR0913, PLR0917
    spike_bin: str,
    nm_bin: str,
    objcopy_bin: str,
    elf_path: Path,
    isa: str,
    mem_regions: list[tuple[int, int]],
    tohost_symbol: str,
    entry_symbol: str = "_start",
    timeout_s: float = 60.0,
) -> SpikeRunResult:
    """Run elf_path under Spike until it writes tohost, or timeout_s passes.

    Parameters
    ----------
    spike_bin : str
        `spike` binary name/path (see spike_exec.require_spike).
    nm_bin : str
        `nm` binary for the target toolchain.
    objcopy_bin : str
        `objcopy` binary for the target toolchain.
    elf_path : Path
        Compiled test ELF to run.
    isa : str
        `--isa=` value; should match the test's own march.
    mem_regions : list of (int, int)
        (base, size) byte pairs, one per region of real memory.
    tohost_symbol : str
        Symbol the program writes its verdict to.
    entry_symbol : str, optional
        Symbol execution starts at.
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
    spike = require_spike(spike_bin)
    entry_pc = symbol_address(nm_bin, elf_path, entry_symbol)
    with prepared_elf(objcopy_bin, nm_bin, elf_path, tohost_symbol) as elf:
        cmd = spike_command(spike, isa, mem_regions, entry_pc, elf)
        try:
            proc = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            return SpikeRunResult(False, None, f"timed out after {timeout_s}s")
    return SpikeRunResult(
        proc.returncode == 0, proc.returncode, proc.stdout + proc.stderr
    )
