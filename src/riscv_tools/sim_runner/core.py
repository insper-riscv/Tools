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

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def expand_env(text: str) -> str:
    """Replace `$VAR` and `${VAR}` in text from the environment.

    Parameters
    ----------
    text : str
        A path or template from the config.

    Returns
    -------
    str
        text with every variable replaced.

    Raises
    ------
    SystemExit
        A variable is not set, naming it: GHDL would otherwise report a
        file it cannot find, far from the cause.
    """
    expanded = os.path.expandvars(text)
    unset = sorted(set(re.findall(r"\$\{?(\w+)\}?", expanded)))
    if unset:
        raise SystemExit(
            f"{text!r} uses an environment variable that is not set: {', '.join(unset)}"
        )
    return expanded


def build_libraries(
    libraries: dict[str, list[str]],
    ghdl_std: str,
    ghdl_flags: list[str],
    libraries_dir: Path,
) -> None:
    """Analyze each VHDL library into libraries_dir, once for a whole suite.

    cocotb_tools.runner builds every source into a single library, so a
    library a design instantiates by name (e.g. altera_mf) is analyzed
    here first and then found with `-P<libraries_dir>`, instead of once
    per test: altera_mf alone is 50 thousand lines.

    Parameters
    ----------
    libraries : dict of {str: list of str}
        {library name: source files, in dependency order}, with
        absolute paths: GHDL runs in libraries_dir.
    ghdl_std : str
        GHDL `--std=` value.
    ghdl_flags : list of str
        Extra GHDL arguments (sim.ghdl_flags).
    libraries_dir : Path
        Directory the analyzed libraries go into (created, and emptied
        first so a previous run's units do not linger).
    """
    if libraries_dir.exists():
        shutil.rmtree(libraries_dir)
    libraries_dir.mkdir(parents=True)

    for name, sources in libraries.items():
        print(f"Analyzing library {name} ({len(sources)} file(s))")
        subprocess.run(
            [
                "ghdl",
                "-a",
                f"--std={ghdl_std}",
                f"--work={name}",
                *ghdl_flags,
                *sources,
            ],
            cwd=libraries_dir,
            check=True,
            stdout=subprocess.DEVNULL,
        )


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
    ram_base: int = 0,
    golden_path: Path | None = None,
    ghdl_flags: list[str] | None = None,
    libraries_dir: Path | None = None,
    run_files: dict[str, Path] | None = None,
    extra_env: dict[str, str] | None = None,
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
    ram_base : int, optional
        memory.ram_base — passed through as RAM_BASE so the testbench
        can convert its own bus-snooped (absolute) RAM addresses into
        the same RAM-relative convention golden_path's keys use,
        without hardcoding it (see mailbox.word_offset). Default 0.
    golden_path : Path, optional
        This test's golden.json (manifest entry "golden"), for a
        "memory"-kind test — passed through as GOLDEN_PATH so the
        testbench can do the same RAM-vs-golden compare
        orchestrator.run_one does for real hardware, from its own
        bus-snooped reconstruction of RAM's final content (cocotb's
        VPI can't read a memory array directly — see a project's own
        sim/test_c_program.py). None (the default) omits it — a
        "unit"-kind test has no golden.json to check.
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
    ghdl_flags : list of str, optional
        Extra GHDL arguments for the analyze/elaborate and run steps
        (sim.ghdl_flags).
    libraries_dir : Path, optional
        Where `build_libraries` analyzed the design's extra libraries;
        GHDL is pointed at it with `-P`.
    run_files : dict of {str: Path}, optional
        {file name: source} copied into build_dir, the directory GHDL
        runs in, before the simulation starts (sim.run_files).
    extra_env : dict of {str: str}, optional
        Environment variables added for the test module (sim.env).

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

    # Same arguments at every GHDL step: analyze/elaborate and run each
    # need the standard, the extra flags and the libraries' location.
    ghdl_args = [f"--std={ghdl_std}", *(ghdl_flags or [])]
    if libraries_dir is not None:
        ghdl_args.append(f"-P{libraries_dir.resolve()}")

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
    for name, source in (run_files or {}).items():
        shutil.copyfile(source, Path(build_dir) / name)

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
            test_args=ghdl_args,
            results_xml=str(results_xml),
            extra_env={
                **(extra_env or {}),
                "ROM_HEX": str(Path(hex_path).resolve()),
                "TEST_NAME": test_name,
                "RAM_BASE": str(ram_base),
                "GOLDEN_PATH": str(Path(golden_path).resolve()) if golden_path else "",
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


# The two boot ROM images are the same kind of independent input as the
# rest; bundling them would add a type for one caller.
def run_suite(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    manifest: list[dict[str, Any]],
    root: Path,
    build_dir: Path,
    boot_rom_hex_path: Path | None = None,
    boot_rom_mif_path: Path | None = None,
) -> dict[str, bool]:
    """Run every test in manifest under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses sim.toplevel/vhdl_sources/
        test_module/ghdl_std/parameters, and the optional
        ghdl_flags/libraries/run_files/env/image (see __config__.py).
    manifest : list of dict of {str: Any}
        The full test list (from `compile --emit hex`'s or
        `--emit mif`'s manifest.json) — each entry needs "name" and
        its image ("hex", or "mif" when sim.image is "mif"), plus
        "golden" for a "memory"-kind entry (see run_test's
        golden_path).
    root : Path
        The consuming project's root directory, entry["hex"] is
        relative to this, and vhdl_sources are resolved relative to
        this too.
    build_dir : Path
        Base directory for per-test GHDL build+run artifacts — each
        test gets its own build_dir/<name>/ subdirectory.
    boot_rom_hex_path : Path, optional
        Path to the FIXED, shared bootloader's compiled .hex (see
        boot_rom.S) — built once by the caller, not per test, unlike
        hex_path below. Made available to sim.parameters templates as
        `{boot_rom_hex_path}`, the same way `{hex_path}` exposes each
        test's own image. A project whose sim toplevel has no such
        generic (no 3-memory BOOT_ROM/FLASH split) can simply omit it.
    boot_rom_mif_path : Path, optional
        The same bootloader as a .mif, for a design whose boot ROM is a
        memory IP initialized from a .mif (sim.image "mif"). Exposed to
        the templates as `{boot_rom_mif_path}`.

    Returns
    -------
    dict of {str: bool}
        A {test_name: passed} dict, one entry per manifest test, in
        manifest order.
    """
    # cocotb_tools.runner's cocotb subprocess inherits PYTHONPATH from
    # *this* process' sys.path (see Simulator._set_env) — needed for
    # sim.test_module (a project-root-relative dotted path, e.g.
    # "tools.riscv_build.sim.test_c_program") to import at all when
    # riscv-tools itself runs as an installed console script rather
    # than via `python -m` from the project root (confirmed
    # empirically: without this, cocotb's subprocess raised
    # "ModuleNotFoundError: No module named 'tools'").
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    sim_cfg = cfg["sim"]
    image_key = "mif" if sim_cfg["image"] == "mif" else "hex"
    ghdl_flags: list[str] = list(sim_cfg["ghdl_flags"])
    # `root / <absolute path>` is that absolute path, so a variable that
    # expands to one (e.g. Quartus' install directory) is expanded first.
    vhdl_sources = [str(root / expand_env(src)) for src in sim_cfg["vhdl_sources"]]
    parameter_templates: dict[str, Any] = sim_cfg.get("parameters") or {}

    libraries_dir: Path | None = None
    if sim_cfg["libraries"]:
        libraries_dir = build_dir / "libraries"
        build_libraries(
            {
                name: [str(root / expand_env(src)) for src in files]
                for name, files in sim_cfg["libraries"].items()
            },
            sim_cfg["ghdl_std"],
            ghdl_flags,
            libraries_dir,
        )

    def resolved(path: Path | None) -> str:
        return str(path.resolve()) if path else ""

    results: dict[str, bool] = {}
    for entry in manifest:
        name = str(entry["name"])
        print(f"\n=== {name} ({entry['march']}) ===")
        image_path = root / entry[image_key]
        # Lets a project's own sim.parameters, sim.run_files and
        # sim.env reference this test's compiled image (e.g. a VHDL
        # generic that loads the ROM image by path, see
        # sim_runner.__config__) without hardcoding one. The boot ROM
        # paths are the SAME for every entry (built once by the
        # caller); still routed through .format() per test so a
        # project's config can reference them exactly like the test's
        # own image, e.g. `BOOT_ROM_FILE: "{boot_rom_hex_path}"`.
        names = {
            "hex_path": resolved(image_path) if image_key == "hex" else "",
            "mif_path": resolved(image_path) if image_key == "mif" else "",
            "boot_rom_hex_path": resolved(boot_rom_hex_path),
            "boot_rom_mif_path": resolved(boot_rom_mif_path),
        }

        def fill(value: Any, names: dict[str, str] = names) -> Any:
            return value.format(**names) if isinstance(value, str) else value

        parameters: dict[str, Any] = {
            k: fill(v) for k, v in parameter_templates.items()
        }
        golden_path = root / entry["golden"] if "golden" in entry else None
        results[name] = run_test(
            toplevel=sim_cfg["toplevel"],
            vhdl_sources=vhdl_sources,
            ghdl_std=sim_cfg["ghdl_std"],
            test_module=sim_cfg["test_module"],
            hex_path=image_path,
            test_name=name,
            build_dir=build_dir / name,
            parameters=parameters,
            ram_base=cfg["memory"]["ram_base"],
            golden_path=golden_path,
            ghdl_flags=ghdl_flags,
            libraries_dir=libraries_dir,
            run_files={
                file_name: Path(fill(source))
                for file_name, source in sim_cfg["run_files"].items()
            },
            extra_env={k: str(fill(v)) for k, v in sim_cfg["env"].items()},
        )
        print(f"{name}: {'PASS' if results[name] else 'FAIL'}")

    return results
