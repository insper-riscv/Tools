"""Drive the cocotb/GHDL simulation of a project's tests.

The project's own cocotb test module knows the VHDL signal hierarchy
and polls the PASS/FAIL mailbox from simulated signals. This module
targets `cocotb_tools.runner` (cocotb 2.0 or later).
"""

import shutil
from pathlib import Path
from typing import Any, NotRequired, Required, TypedDict, Unpack

from cocotb_tools.check_results import get_results
from cocotb_tools.runner import VHDL, get_runner


class RunOptions(TypedDict):
    """The keyword settings of `run_test` besides the design itself."""

    test_name: Required[str]
    build_dir: Required[Path]
    parameters: NotRequired[dict[str, Any] | None]
    ram_base: NotRequired[int]
    golden_path: NotRequired[Path | None]
    ghdl_flags: NotRequired[list[str] | None]
    libraries_dir: NotRequired[Path | None]
    run_files: NotRequired[dict[str, Path] | None]
    extra_env: NotRequired[dict[str, str] | None]
    ghdl_run_flags: NotRequired[list[str] | None]


def run_test(
    toplevel: str,
    vhdl_sources: list[str],
    ghdl_std: str,
    test_module: str,
    hex_path: Path,
    **options: Unpack[RunOptions],
) -> bool:
    """Build (if needed) and run one test under cocotb/GHDL.

    Parameters
    ----------
    toplevel : str
        Top-level VHDL entity (sim.toplevel).
    vhdl_sources : list of str
        VHDL files in dependency order (sim.vhdl_sources).
    ghdl_std : str
        GHDL `--std=` value (sim.ghdl_std, for example "08").
    test_module : str
        The project's cocotb test module (sim.test_module). It reads
        the ROM image from ROM_HEX and the test name from TEST_NAME.
    hex_path : Path
        This test's compiled .hex.
    **options : Unpack[RunOptions]
        Keyword settings. `test_name` and `build_dir` are required.
    test_name : str
        This test's name, passed as TEST_NAME.
    build_dir : Path
        GHDL build and run directory, one per test.
    ram_base : int, optional
        memory.ram_base, passed as RAM_BASE. Default 0.
    golden_path : Path, optional
        golden.json of a "memory"-kind test, passed as GOLDEN_PATH.
        None omits it.
    parameters : dict of {str: Any}, optional
        VHDL generics for toplevel (sim.parameters), applied at the
        run step. Default: none.
    ghdl_flags : list of str, optional
        Extra GHDL arguments (sim.ghdl_flags).
    libraries_dir : Path, optional
        Where the extra libraries were analyzed; GHDL gets `-P`.
    run_files : dict of {str: Path}, optional
        {name: source} copied into build_dir before the run.
    extra_env : dict of {str: str}, optional
        Environment variables for the test module (sim.env).
    ghdl_run_flags : list of str, optional
        GHDL simulation options (for example `--max-stack-alloc=0`).

    Returns
    -------
    bool
        True if every cocotb testcase passed.

    Raises
    ------
    SystemExit
        cocotb did not produce results.xml (the simulation crashed).
    """
    build_dir = options["build_dir"]
    ghdl_args = _ghdl_args(
        ghdl_std, options.get("ghdl_flags"), options.get("libraries_dir")
    )

    runner = get_runner("ghdl")
    runner.build(
        sources=[VHDL(Path(p)) for p in vhdl_sources],
        hdl_toplevel=toplevel,
        always=True,
        build_dir=build_dir,
        build_args=ghdl_args,
    )

    # GHDL runs in build_dir (test_dir defaults to it), so a file the
    # design opens by a fixed name goes there.
    for name, source in (options.get("run_files") or {}).items():
        shutil.copyfile(source, Path(build_dir) / name)

    # results.xml gets a fixed name, so the results can be read back
    # below.
    results_xml = Path(build_dir) / "results.xml"

    # Runner.test() raises SystemExit when any testcase failed, even
    # though the simulation completed and wrote a normal results.xml.
    # A failed test is an expected outcome, so SystemExit is caught and
    # turned into a False return; only a missing results.xml (a crash
    # before any results existed) propagates.
    try:
        runner.test(
            hdl_toplevel=toplevel,
            hdl_toplevel_lang="vhdl",
            test_module=test_module,
            build_dir=build_dir,
            # GHDL's run step (`ghdl -r`) needs --std= too, not just
            # analyze/elaborate: without it, `-r` can't find an entity
            # that was analyzed under a non-default std, since GHDL
            # keeps per-standard library state.
            test_args=ghdl_args,
            # GHDL takes a simulation option only after the top-level
            # unit, where cocotb puts the plusargs
            plusargs=options.get("ghdl_run_flags") or [],
            results_xml=str(results_xml),
            extra_env=_test_env(hex_path, options),
            parameters=options.get("parameters"),
        )
    except SystemExit:
        if not results_xml.is_file():
            raise
    _num_tests, num_failed = get_results(results_xml)
    return num_failed == 0


def _ghdl_args(
    ghdl_std: str, ghdl_flags: list[str] | None, libraries_dir: Path | None
) -> list[str]:
    """Build the arguments that every GHDL step needs.

    Parameters
    ----------
    ghdl_std : str
        GHDL `--std=` value.
    ghdl_flags : list of str or None
        Extra GHDL arguments (sim.ghdl_flags).
    libraries_dir : Path or None
        Where the design's extra libraries were analyzed, if any.

    Returns
    -------
    list of str
        The standard, the extra flags and the libraries' location.
    """
    args = [f"--std={ghdl_std}", *(ghdl_flags or [])]
    if libraries_dir is not None:
        args.append(f"-P{libraries_dir.resolve()}")
    return args


def _test_env(hex_path: Path, options: RunOptions) -> dict[str, str]:
    """Build the environment the cocotb test module reads.

    Parameters
    ----------
    hex_path : Path
        This test's compiled .hex.
    options : RunOptions
        The keyword settings of run_test.

    Returns
    -------
    dict of {str: str}
        sim.env plus ROM_HEX, TEST_NAME, RAM_BASE and GOLDEN_PATH.
    """
    golden_path = options.get("golden_path")
    return {
        **(options.get("extra_env") or {}),
        "ROM_HEX": str(Path(hex_path).resolve()),
        "TEST_NAME": options["test_name"],
        "RAM_BASE": str(options.get("ram_base", 0)),
        "GOLDEN_PATH": str(Path(golden_path).resolve()) if golden_path else "",
    }
