"""Drive cocotb/GHDL simulation, the simulation-side counterpart to `orchestrator`.

`orchestrator` drives real hardware over JTAG instead. Owns no
DUT-specific knowledge itself — the project's own cocotb test_module
(see __config__.py) knows the actual VHDL signal hierarchy and polls
the PASS/FAIL mailbox, the same convention `mailbox` uses for real
hardware, just read directly from simulated signals instead of JTAG.

cocotb-tools is imported lazily inside the functions below, not at
module level, so importing riscv_tools doesn't require it to be
installed for projects that only use the real-hardware side (see
pyproject.toml: cocotb/cocotb-tools are an optional "sim" extra, not a
hard dependency). Note cocotb 2.0 split its Python test-runner API
(get_runner/build/test) out of the main `cocotb` package into a
separate `cocotb-tools` package, imported as `cocotb_tools.runner` —
this module targets that (cocotb>=2.0), not the older `cocotb.runner`
some 1.x docs/examples still reference.
"""

from pathlib import Path
from typing import Any


# Each arg is an independent cocotb/GHDL run setting — not bundleable
# without a config object this module doesn't otherwise need.
def run_test(  # noqa: PLR0913, PLR0917
    toplevel: str,
    vhdl_sources: list[str],
    ghdl_std: str,
    test_module: str,
    hex_path: Path,
    test_name: str,
    build_dir: Path,
    parameters: dict[str, Any] | None = None,
) -> bool:
    """Build (if needed) and run one test under cocotb/GHDL.

    Parameters
    ----------
    toplevel : str
        Top-level VHDL entity name (sim.toplevel).
    vhdl_sources : list of str
        VHDL source file paths, in dependency order
        (sim.vhdl_sources).
    ghdl_std : str
        GHDL `--std=` value (sim.ghdl_std, default "08" — VHDL-2008 /
        IEEE Std 1076-2008).
    test_module : str
        The project's own cocotb test module name (sim.test_module) —
        receives this test's ROM image via the ROM_HEX environment
        variable, and this test's name via TEST_NAME, matching the
        convention the project's testbench expects (see e.g. a
        project's sim/test_c_program.py).
    hex_path : Path
        Path to this test's compiled .hex (from
        bin_to_image.bin_to_hex).
    test_name : str
        This test's name (manifest entry "name") — passed through as
        TEST_NAME.
    build_dir : Path
        Directory for GHDL's build+run artifacts (kept separate per
        test so parallel/repeated runs don't clobber each other's
        elaborated design).
    parameters : dict of {str: Any}, optional
        VHDL generics to set on toplevel (sim.parameters, e.g. a
        project's own `ROM_FILE`/memory-depth generics — see
        sim_runner.__config__.DEFAULTS). Passed to
        cocotb_tools.runner.Runner.test(), not .build(): GHDL only
        applies generics at its `-r` (run) step, not `-i`/`-m`
        (analyze/elaborate) — confirmed by reading
        cocotb_tools.runner.Ghdl's own `_test_command`/`_build_command`,
        which only calls `_get_parameter_options` from the former.
        Defaults to no overrides (whatever defaults toplevel's own
        VHDL declares).

    Returns
    -------
    bool
        True if every cocotb testcase passed, False if any failed.

    Raises
    ------
    SystemExit
        cocotb's results.xml wasn't produced at all (e.g. the
        simulation crashed before finishing, rather than running to
        completion and failing normally) — see
        cocotb_tools.runner.get_results.
    """
    from cocotb_tools.check_results import get_results  # noqa: PLC0415
    from cocotb_tools.runner import VHDL, get_runner  # noqa: PLC0415

    runner = get_runner("ghdl")
    runner.build(
        sources=[VHDL(Path(p)) for p in vhdl_sources],
        hdl_toplevel=toplevel,
        always=True,
        build_dir=build_dir,
        build_args=[f"--std={ghdl_std}"],
    )

    # GHDL's run step (`ghdl -r`) needs --std= too, not just analyze/
    # elaborate (`-i`/`-m` via build_args above) — confirmed empirically:
    # without it, `-r` can't find an entity that was analyzed under a
    # non-default std, since GHDL keeps per-standard library state.
    # Runner.test() feeds this into `-r` via test_args (see
    # cocotb_tools.runner.Ghdl: `ghdl_run_args = self.test_args`).
    #
    # A fixed results_xml name (rather than cocotb's own default,
    # which is derived from the pytest test name when run under
    # pytest — not useful here) so we know exactly where to re-read
    # results from below.
    results_xml = Path(build_dir) / "results.xml"

    # Unlike the older cocotb.runner (1.x), cocotb_tools.runner's
    # Runner.test() (2.x) raises SystemExit itself when any testcase
    # failed — confirmed empirically (a deliberately-failing cocotb
    # test here raised SystemExit(1) even though the simulation ran to
    # completion and produced a normal results.xml with FAIL=1). A
    # failed TEST isn't a crash of the whole suite, so that expected
    # case is caught and translated into a plain False return; only a
    # missing results.xml (genuine crash before any results existed)
    # propagates.
    try:
        runner.test(
            hdl_toplevel=toplevel,
            hdl_toplevel_lang="vhdl",
            test_module=test_module,
            build_dir=build_dir,
            test_args=[f"--std={ghdl_std}"],
            results_xml=str(results_xml),
            extra_env={
                "ROM_HEX": str(Path(hex_path).resolve()),
                "TEST_NAME": test_name,
            },
            parameters=parameters,
        )
    except SystemExit:
        if not results_xml.is_file():
            raise
        _num_tests, num_failed = get_results(results_xml)
        return num_failed == 0

    _num_tests, num_failed = get_results(results_xml)
    return num_failed == 0


def run_suite(
    cfg: dict[str, Any], manifest: list[dict[str, Any]], root: Path, build_dir: Path
) -> dict[str, bool]:
    """Run every test in manifest under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses sim.toplevel/vhdl_sources/
        test_module/ghdl_std/parameters.
    manifest : list of dict of {str: Any}
        The full test list (from `compile --emit hex`'s
        manifest.json) — each entry needs "name" and "hex".
    root : Path
        The consuming project's root directory, entry["hex"] is
        relative to this, and vhdl_sources are resolved relative to
        this too.
    build_dir : Path
        Base directory for per-test GHDL build+run artifacts — each
        test gets its own build_dir/<name>/ subdirectory.

    Returns
    -------
    dict of {str: bool}
        A {test_name: passed} dict, one entry per manifest test, in
        manifest order.
    """
    vhdl_sources = [str(root / src) for src in cfg["sim"]["vhdl_sources"]]
    parameter_templates: dict[str, Any] = cfg["sim"].get("parameters") or {}

    results: dict[str, bool] = {}
    for entry in manifest:
        name = str(entry["name"])
        print(f"\n=== {name} ({entry['march']}) ===")
        hex_path = root / entry["hex"]
        # Lets a project's own sim.parameters (e.g. a VHDL generic
        # that loads the ROM image by path, see sim_runner.__config__)
        # reference this test's compiled .hex without hardcoding one.
        parameters: dict[str, Any] = {
            k: v.format(hex_path=str(hex_path.resolve())) if isinstance(v, str) else v
            for k, v in parameter_templates.items()
        }
        results[name] = run_test(
            toplevel=cfg["sim"]["toplevel"],
            vhdl_sources=vhdl_sources,
            ghdl_std=cfg["sim"]["ghdl_std"],
            test_module=cfg["sim"]["test_module"],
            hex_path=hex_path,
            test_name=name,
            build_dir=build_dir / name,
            parameters=parameters,
        )
        print(f"{name}: {'PASS' if results[name] else 'FAIL'}")

    return results
