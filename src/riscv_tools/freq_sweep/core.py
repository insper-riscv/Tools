"""Edit a project's PLL source to reprogram its output clock frequency.

Generalizes RV32IM's original ad hoc `set_pll_freq()` (a fixed regex
against one specific `pll_0002.v` layout): the parameter-name
patterns, unit strings, and how many phase-shifted clock outputs to
rewrite all come from a project's own `freq_sweep:` config section
(see __config__.py) instead of being hardcoded here — a project with
a single-phase PLL, a differently named megafunction instance, or a
VHDL rather than Verilog PLL wrapper (as long as it uses the same
`.param("value")` instantiation syntax) configures this without
touching this module's code.

No hardware/JTAG interaction here — purely a text rewrite of the PLL
source file. Recompiling/reprogramming after the edit is the caller's
job (see orchestrator.run_freq_sweep_at).
"""

import re
from pathlib import Path

# 1 MHz's period, in picoseconds — the constant this module's period
# math is built on (see set_pll_freq's Notes: freq_unit/phase_unit
# only control the string suffix written, not this arithmetic, which
# always assumes MHz-in/ps-out, matching Quartus' altpll convention).
_PS_PER_MHZ_PERIOD = 1_000_000


def _phase_offset_ps(idx: int, period_ps: int, phase_count: int) -> int:
    """Compute one of `phase_count` equally spaced phase offsets.

    Parameters
    ----------
    idx : int
        Which phase-shifted output (0-indexed) to compute the offset
        for.
    period_ps : int
        The clock period, in picoseconds.
    phase_count : int
        Total number of equally spaced phase outputs (e.g. 3 for a
        0/120/240-degree three-way PLL).

    Returns
    -------
    int
        idx's phase offset in picoseconds (0 for idx=0), rounded down
        to the nearest ps.
    """
    return (idx * period_ps) // phase_count


def set_pll_freq(  # noqa: PLR0913, PLR0917
    pll_file: Path,
    mhz: float,
    phase_count: int,
    freq_param_template: str,
    phase_param_template: str,
    freq_unit: str,
    phase_unit: str,
) -> None:
    """Rewrite a PLL source's clock frequency (and phase offsets) in place.

    For each of `phase_count` clock outputs, replaces
    `.<freq_param>("...")`  with the new frequency and
    `.<phase_param>("...")` with that output's recomputed phase
    offset — so multi-phase outputs stay proportionally spaced at the
    new frequency (see _phase_offset_ps). A parameter pair that
    doesn't appear in the file (e.g. phase_count set too high for
    what the PLL source actually declares) is silently left
    unchanged, matching `re.sub`'s no-match behavior.

    Parameters
    ----------
    pll_file : Path
        Path to the PLL source file to rewrite.
    mhz : float
        New clock frequency, in MHz, for every phase output.
    phase_count : int
        How many `.<freq_param>{idx}(...)`/`.<phase_param>{idx}(...)`
        pairs to rewrite, idx = 0..phase_count-1 (see
        freq_sweep.__config__.DEFAULTS).
    freq_param_template : str
        "{idx}"-templated parameter name, e.g.
        "output_clock_frequency{idx}".
    phase_param_template : str
        "{idx}"-templated parameter name, e.g. "phase_shift{idx}".
    freq_unit : str
        Unit suffix written after the frequency value (e.g. "MHz").
    phase_unit : str
        Unit suffix written after the phase value (e.g. "ps").

    Returns
    -------
    None

    Raises
    ------
    FileNotFoundError
        pll_file doesn't exist.
    """
    text = pll_file.read_text()
    period_ps = round(_PS_PER_MHZ_PERIOD / mhz)
    freq_str = f"{mhz:.6f} {freq_unit}"

    for idx in range(phase_count):
        phase_ps = _phase_offset_ps(idx, period_ps, phase_count)
        freq_param_name = freq_param_template.format(idx=idx)
        phase_param_name = phase_param_template.format(idx=idx)

        text = re.sub(
            rf'\.{re.escape(freq_param_name)}\("[^"]+"\)',
            f'.{freq_param_name}("{freq_str}")',
            text,
        )
        text = re.sub(
            rf'\.{re.escape(phase_param_name)}\("[^"]+"\)',
            f'.{phase_param_name}("{phase_ps} {phase_unit}")',
            text,
        )

    pll_file.write_text(text)


def get_pll_freq(
    pll_file: Path, freq_param_template: str, freq_unit: str
) -> float | None:
    """Read a PLL source's currently configured clock frequency.

    Reads phase 0 (idx=0) only — set_pll_freq always sets every phase
    output to the same frequency, so any one of them reflects the
    current setting.

    Parameters
    ----------
    pll_file : Path
        Path to the PLL source file to read.
    freq_param_template : str
        "{idx}"-templated parameter name (see set_pll_freq).
    freq_unit : str
        Unit suffix expected after the frequency value (see
        set_pll_freq).

    Returns
    -------
    float or None
        The currently configured frequency in MHz, or None if
        `freq_param_template.format(idx=0)` isn't found in pll_file.
    """
    text = pll_file.read_text()
    freq_param = re.escape(freq_param_template.format(idx=0))
    unit = re.escape(freq_unit)
    m = re.search(rf'\.{freq_param}\("([\d.]+)\s*{unit}"\)', text)
    return float(m.group(1)) if m else None
