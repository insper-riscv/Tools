"""Drive cocotb/GHDL simulation, the sim side of `orchestrator`.

`orchestrator` drives real hardware over JTAG instead. Owns no
DUT-specific knowledge itself; the project's own cocotb test_module
(see __config__.py) knows the actual VHDL signal hierarchy and polls
the PASS/FAIL mailbox, the same convention `mailbox` uses for real
hardware, just read directly from simulated signals instead of JTAG.

Note cocotb 2.0 split its Python test-runner API
(get_runner/build/test) out of the main `cocotb` package into
`cocotb_tools.runner`; this module targets that (cocotb>=2.0), not the
older `cocotb.runner` some 1.x docs/examples still reference.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, Required, TypedDict, Unpack

from cocotb_tools.check_results import get_results
from cocotb_tools.runner import VHDL, get_runner


def _profile_build_dir(build_dir: Path, sim_cfg: dict[str, Any]) -> Path:
    """Return a stable, path-safe work directory for one profile."""
    toplevel = str(sim_cfg["toplevel"])
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "-", toplevel).strip("._-")
    readable = (readable or "toplevel")[:48]
    identity = json.dumps(
        sim_cfg, sort_keys=True, separators=(",", ":"), default=str
    )
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return build_dir / f"{readable}-{fingerprint}"


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
            f"{text!r} uses an environment variable that is not set: "
            f"{', '.join(unset)}"
        )
    return expanded


def build_libraries(
    libraries: dict[str, list[str]],
    ghdl_std: str,
    ghdl_flags: list[str],
    libraries_dir: Path,
) -> None:
    """Analyze each VHDL library into libraries_dir, once per suite.

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


class BootRomImages(TypedDict, total=False):
    """The optional boot ROM images that `run_suite` passes on."""

    boot_rom_hex_path: Path | None
    boot_rom_mif_path: Path | None


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
        Top-level VHDL entity name (sim.toplevel).
    vhdl_sources : list of str
        VHDL source file paths, in dependency order
        (sim.vhdl_sources).
    ghdl_std : str
        GHDL `--std=` value (sim.ghdl_std, default "08", VHDL-2008 /
        IEEE Std 1076-2008).
    test_module : str
        The project's own cocotb test module name (sim.test_module),
        receives this test's ROM image via the ROM_HEX environment
        variable, and this test's name via TEST_NAME, matching the
        convention the project's testbench expects (see e.g. a
        project's sim/test_c_program.py).
    hex_path : Path
        Path to this test's compiled .hex (from
        bin_to_image.bin_to_hex).
    **options : Unpack[RunOptions]
        Keyword settings, described below: `test_name` and `build_dir`
        are required, the others optional.
    test_name : str
        This test's name (manifest entry "name"), passed through as
        TEST_NAME.
    build_dir : Path
        Directory for GHDL's build+run artifacts (kept separate per
        test so parallel/repeated runs don't clobber each other's
        elaborated design).
    ram_base : int, optional
        memory.ram_base, passed through as RAM_BASE so the testbench
        can convert its own bus-snooped (absolute) RAM addresses into
        the same RAM-relative convention golden_path's keys use,
        without hardcoding it (see mailbox.word_offset). Default 0.
    golden_path : Path, optional
        This test's golden.json (manifest entry "golden"), for a
        "memory"-kind test, passed through as GOLDEN_PATH so the
        testbench can do the same RAM-vs-golden compare
        orchestrator.run_one does for real hardware, from its own
        bus-snooped reconstruction of RAM's final content (cocotb's
        VPI can't read a memory array directly; see a project's own
        sim/test_c_program.py). None (the default) omits it, a
        "unit"-kind test has no golden.json to check.
    parameters : dict of {str: Any}, optional
        VHDL generics to set on toplevel (sim.parameters, e.g. a
        project's own `ROM_FILE`/memory-depth generics; see
        sim_runner.__config__.DEFAULTS). Passed to
        cocotb_tools.runner.Runner.test(), not .build(): GHDL only
        applies generics at its `-r` (run) step, not `-i`/`-m`
        (analyze/elaborate), confirmed by reading
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
    ghdl_run_flags : list of str, optional
        GHDL simulation options, which the analyze and elaborate steps
        reject (for example `--max-stack-alloc=0`).

    Returns
    -------
    bool
        True if every cocotb testcase passed, False if any failed.

    Raises
    ------
    SystemExit
        cocotb's results.xml wasn't produced at all (e.g. the
        simulation crashed before finishing, rather than running to
        completion and failing normally); see
        cocotb_tools.runner.get_results.
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

    # A fixed results_xml name (rather than cocotb's own default,
    # which is derived from the pytest test name when run under
    # pytest, not useful here) so we know exactly where to re-read
    # results from below.
    results_xml = Path(build_dir) / "results.xml"

    # Unlike the older cocotb.runner (1.x), cocotb_tools.runner's
    # Runner.test() (2.x) raises SystemExit itself when any testcase
    # failed, confirmed empirically (a deliberately-failing cocotb
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


def extend_python_path(root: Path, entries: list[str]) -> None:
    """Put directories on the module search path, ahead of the rest.

    The simulation's test module is imported by a cocotb subprocess that
    inherits `sys.path` from this process, so a module is found only if
    its directory is on it.

    Parameters
    ----------
    root : Path
        The project root that relative entries are resolved against.
    entries : list of str
        Directories, relative to `root` (or absolute). Ones already on
        the path are left where they are.

    Returns
    -------
    None
        Inserts into `sys.path`.
    """
    for entry in entries:
        path = str((root / entry).resolve())
        if path not in sys.path:
            sys.path.insert(0, path)


def _resolved(path: Path | None) -> str:
    """Return a path as an absolute string, or "" when it is None."""
    return str(path.resolve()) if path else ""


@dataclass(frozen=True)
class _Suite:
    """What every test of a suite shares, resolved once."""

    cfg: dict[str, Any]
    root: Path
    profile_build_dir: Path
    vhdl_sources: list[str]
    libraries_dir: Path | None
    boot_roms: BootRomImages

    def run_entry(self, entry: dict[str, Any]) -> bool:
        """Run one manifest test under cocotb/GHDL.

        Parameters
        ----------
        entry : dict of {str: Any}
            A manifest entry.

        Returns
        -------
        bool
            Whether the test passed.
        """
        sim_cfg = self.sim_cfg
        name = str(entry["name"])
        print(f"\n=== {name} ({entry['march']}) ===")
        image_key = "mif" if sim_cfg["image"] == "mif" else "hex"
        image_path = self.root / entry[image_key]
        # Lets a project's own sim.parameters, sim.run_files and
        # sim.env reference this test's compiled image (e.g. a VHDL
        # generic that loads the ROM image by path, see
        # sim_runner.__config__) without hardcoding one. The boot ROM
        # paths are the SAME for every entry (built once by the
        # caller); still routed through .format() per test so a
        # project's config can reference them exactly like the test's
        # own image, e.g. `BOOT_ROM_FILE: "{boot_rom_hex_path}"`.
        names = {
            "hex_path": _resolved(image_path) if image_key == "hex" else "",
            "mif_path": _resolved(image_path) if image_key == "mif" else "",
            "boot_rom_hex_path": _resolved(
                self.boot_roms.get("boot_rom_hex_path")
            ),
            "boot_rom_mif_path": _resolved(
                self.boot_roms.get("boot_rom_mif_path")
            ),
        }

        def fill(value: Any) -> Any:
            return value.format(**names) if isinstance(value, str) else value

        templates: dict[str, Any] = sim_cfg.get("parameters") or {}
        golden_path = (
            self.root / entry["golden"] if "golden" in entry else None
        )
        passed = run_test(
            toplevel=sim_cfg["toplevel"],
            vhdl_sources=self.vhdl_sources,
            ghdl_std=sim_cfg["ghdl_std"],
            test_module=sim_cfg["test_module"],
            hex_path=image_path,
            test_name=name,
            build_dir=self.profile_build_dir / name,
            parameters={k: fill(v) for k, v in templates.items()},
            ram_base=self.cfg["memory"]["ram_base"],
            golden_path=golden_path,
            ghdl_flags=list(sim_cfg["ghdl_flags"]),
            libraries_dir=self.libraries_dir,
            run_files={
                file_name: Path(fill(source))
                for file_name, source in sim_cfg["run_files"].items()
            },
            extra_env={k: str(fill(v)) for k, v in sim_cfg["env"].items()},
        )
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
        return passed

    @property
    def sim_cfg(self) -> dict[str, Any]:
        """The `sim` section of the config."""
        return self.cfg["sim"]


def run_suite(
    cfg: dict[str, Any],
    manifest: list[dict[str, Any]],
    root: Path,
    build_dir: Path,
    **boot_roms: Unpack[BootRomImages],
) -> dict[str, bool]:
    """Run every test in manifest under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: uses sim.toplevel/vhdl_sources/
        test_module/ghdl_std/parameters, and the optional
        ghdl_flags/libraries/run_files/env/image (see __config__.py).
    manifest : list of dict of {str: Any}
        The full test list (from `compile --emit hex`'s or
        `--emit mif`'s manifest.json); each entry needs "name" and
        its image ("hex", or "mif" when sim.image is "mif"), plus
        "golden" for a "memory"-kind entry (see run_test's
        golden_path).
    root : Path
        The consuming project's root directory, entry["hex"] is
        relative to this, and vhdl_sources are resolved relative to
        this too.
    build_dir : Path
        Base directory for GHDL build+run artifacts. Each simulation
        profile gets a stable, path-safe subdirectory, and each test
        gets a directory below it. The readable prefix identifies the
        top; the fingerprint covers the full sim configuration so stale
        GHDL units cannot cross profiles that happen to share a top.
    boot_rom_hex_path : Path, optional
        Path to the FIXED, shared bootloader's compiled .hex (see
        boot_rom.S), built once by the caller, not per test, unlike
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
    # sim.test_module is a root-relative dotted path (e.g.
    # "tools.riscv_build.sim.test_c_program"): the cocotb subprocess
    # finds it only through the sys.path of this process, also when
    # riscv-tools runs as an installed console script; without it the
    # import fails with "No module named 'tools'".
    sim_cfg = cfg["sim"]
    profile_build_dir = _profile_build_dir(build_dir, sim_cfg)
    extend_python_path(root, [".", *sim_cfg["python_path"]])
    # `root / <absolute path>` is that absolute path, so a variable that
    # expands to one (e.g. Quartus' install directory) is expanded
    # first.
    suite = _Suite(
        cfg=cfg,
        root=root,
        profile_build_dir=profile_build_dir,
        vhdl_sources=[
            str(root / expand_env(src)) for src in sim_cfg["vhdl_sources"]
        ],
        libraries_dir=_build_suite_libraries(sim_cfg, root, profile_build_dir),
        boot_roms=boot_roms,
    )
    return {str(entry["name"]): suite.run_entry(entry) for entry in manifest}


def _build_suite_libraries(
    sim_cfg: dict[str, Any], root: Path, profile_build_dir: Path
) -> Path | None:
    """Analyze the suite's extra VHDL libraries, if it has any.

    Parameters
    ----------
    sim_cfg : dict of {str: Any}
        The `sim` section of the config.
    root : Path
        The project root that library sources are relative to.
    profile_build_dir : Path
        The profile's build directory.

    Returns
    -------
    Path or None
        Where the libraries were analyzed; None when there are none.
    """
    if not sim_cfg["libraries"]:
        return None
    libraries_dir = profile_build_dir / "libraries"
    build_libraries(
        {
            name: [str(root / expand_env(src)) for src in files]
            for name, files in sim_cfg["libraries"].items()
        },
        sim_cfg["ghdl_std"],
        list(sim_cfg["ghdl_flags"]),
        libraries_dir,
    )
    return libraries_dir
