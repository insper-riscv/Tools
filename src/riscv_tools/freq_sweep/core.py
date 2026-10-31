"""Edit a project's PLL source to reprogram its output clock frequency.

The parameter-name patterns, the unit strings and the number of
phase-shifted outputs come from the project's `freq_sweep:` config
section, so any PLL that uses the `.param("value")` instantiation
syntax works. Only the PLL source is rewritten; recompiling and
reprogramming is the caller's job.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# 1 MHz's period, in picoseconds, the constant this module's period
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


@dataclass(frozen=True)
class PllParams:
    """How a PLL source names and formats its clock parameters.

    Attributes
    ----------
    phase_count : int
        How many `.<freq_param>{idx}(...)`/`.<phase_param>{idx}(...)`
        pairs the PLL source declares, idx = 0..phase_count-1 (see
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
    """

    phase_count: int
    freq_param_template: str
    phase_param_template: str
    freq_unit: str
    phase_unit: str


def set_pll_freq(pll_file: Path, mhz: float, params: PllParams) -> None:
    """Rewrite a PLL source's clock frequency and phase offsets.

    For each of `phase_count` clock outputs, replaces
    `.<freq_param>("...")`  with the new frequency and
    `.<phase_param>("...")` with that output's recomputed phase
    offset, so multi-phase outputs stay proportionally spaced at the
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
    params : PllParams
        The PLL source's parameter-name templates, unit suffixes and
        number of phase outputs.

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
    freq_str = f"{mhz:.6f} {params.freq_unit}"

    for idx in range(params.phase_count):
        phase_ps = _phase_offset_ps(idx, period_ps, params.phase_count)
        freq_param_name = params.freq_param_template.format(idx=idx)
        phase_param_name = params.phase_param_template.format(idx=idx)

        text = re.sub(
            rf'\.{re.escape(freq_param_name)}\("[^"]+"\)',
            f'.{freq_param_name}("{freq_str}")',
            text,
        )
        text = re.sub(
            rf'\.{re.escape(phase_param_name)}\("[^"]+"\)',
            f'.{phase_param_name}("{phase_ps} {params.phase_unit}")',
            text,
        )

    pll_file.write_text(text)
