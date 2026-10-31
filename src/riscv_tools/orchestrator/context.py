"""The state and the options shared by the runs of a suite."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools.jtag import JtagLink


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
