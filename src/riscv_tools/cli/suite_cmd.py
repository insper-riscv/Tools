"""The `run` and `sim` subcommands and their test filters."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    boot_rom,
    orchestrator,
    sim_runner,
)
from riscv_tools.cli.common import (
    jtag_link,
    load_manifest,
    start_real_run,
    start_run,
)
from riscv_tools.cli.spike_cmd import print_run_summary
from riscv_tools.orchestrator.runner import RunContext, SuiteOptions


def _split_test_name_groups(groups: list[str] | None) -> list[str]:
    """Expand repeatable comma-separated CLI values, deduplicated."""
    names: list[str] = []
    seen: set[str] = set()
    for group in groups or []:
        for raw_name in group.split(","):
            name = raw_name.strip()
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return names


def _check_filter_names(
    filters: tuple[tuple[str, list[str] | None, list[str]], ...],
    by_name: dict[str, dict[str, Any]],
    manifest_path: Path,
) -> None:
    """Exit with status 1 on an empty or unknown name filter.

    Parameters
    ----------
    filters : tuple of (str, list of str or None, list of str)
        For each option, its flag, raw values and expanded names.
    by_name : dict of {str: dict of {str: Any}}
        The manifest entries by name.
    manifest_path : Path
        Path used in error diagnostics.
    """
    for option, groups, names in filters:
        if groups and not names:
            print(f"{option} requires at least one test name", file=sys.stderr)
            sys.exit(1)
        missing = [name for name in names if name not in by_name]
        if missing:
            print(
                f"{option} names not found in {manifest_path}: "
                f"{', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)


def filter_manifest(
    manifest: list[dict[str, Any]],
    manifest_path: Path,
    only_groups: list[str] | None,
    exclude_groups: list[str] | None,
) -> list[dict[str, Any]]:
    """Select manifest entries requested by repeatable CLI name filters.

    ``--only`` establishes an explicit ordered subset when present;
    otherwise the manifest's own order is kept. ``--exclude`` is then
    applied to that result, so exclusions win when both options name the
    same test. Unknown names and an empty final selection are errors: a
    misspelled exclusion must never silently run the test it meant to
    omit.

    Parameters
    ----------
    manifest : list of dict of {str: Any}
        Original manifest entries.
    manifest_path : Path
        Path used in error diagnostics.
    only_groups : list of str, optional
        Repeatable comma-separated ``--only`` values.
    exclude_groups : list of str, optional
        Repeatable comma-separated ``--exclude`` values.

    Returns
    -------
    list of dict of {str: Any}
        The non-empty filtered manifest.
    """
    by_name = {entry["name"]: entry for entry in manifest}
    only_names = _split_test_name_groups(only_groups)
    exclude_names = _split_test_name_groups(exclude_groups)

    _check_filter_names(
        (
            ("--only", only_groups, only_names),
            ("--exclude", exclude_groups, exclude_names),
        ),
        by_name,
        manifest_path,
    )

    selected = (
        [by_name[name] for name in only_names]
        if only_names
        else list(manifest)
    )
    excluded = set(exclude_names)
    selected = [entry for entry in selected if entry["name"] not in excluded]
    if not selected:
        print(
            f"No tests selected from {manifest_path}; check --only/--exclude",
            file=sys.stderr,
        )
        sys.exit(1)
    return selected


def _select_run_manifest(
    cfg: dict[str, Any],
    args: argparse.Namespace,
    manifest: list[dict[str, Any]],
    manifest_path: Path,
) -> list[dict[str, Any]]:
    """Pick the entries `riscv-tools run` should run.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses orchestrator.interactive.
    args : argparse.Namespace
        Parsed CLI arguments; uses the optional args.only and
        args.exclude.
    manifest : list of dict of {str: Any}
        Every entry of the manifest.
    manifest_path : Path
        Path used in error diagnostics.

    Returns
    -------
    list of dict of {str: Any}
        The non-empty selection.
    """
    # programs that wait for a host to talk to them (a monitor) would
    # only time out in a suite; they run when --only asks for them
    interactive = set(cfg.get("orchestrator", {}).get("interactive", []))
    if not getattr(args, "only", None) and interactive:
        manifest = [
            entry for entry in manifest if entry["name"] not in interactive
        ]
    return filter_manifest(
        manifest,
        manifest_path,
        getattr(args, "only", []),
        getattr(args, "exclude", []),
    )


def _load_progress(
    results_path: Path, requested_names: set[str]
) -> dict[str, bool]:
    """Load the results a stopped run left behind.

    Parameters
    ----------
    results_path : Path
        The run_progress.json of an earlier invocation, if any.
    requested_names : set of str
        The tests this invocation is about; others are dropped.

    Returns
    -------
    dict of {str: bool}
        The already completed tests; empty if there is no file.
    """
    if not results_path.is_file():
        return {}
    done = {
        name: ok
        for name, ok in json.loads(results_path.read_text()).items()
        if name in requested_names
    }
    if done:
        print(
            f"Resuming from {results_path}; {len(done)} "
            f"already-completed test(s) will be skipped"
        )
    return done


def cmd_run(args: argparse.Namespace) -> None:
    """Implement `riscv-tools run`.

    Runs the real-hardware test suite from a manifest.json (see
    orchestrator.run_suite), the full manifest by default, or a
    caller-picked subset via --only/--exclude. Stops early (doesn't
    raise) the moment a test hits a JTAG/hardware failure no automated
    retry can
    fix (orchestrator.NeedsHumanInterventionError); progress is saved
    to <build_dir>/real/run_progress.json as it goes, and simply
    re-running the exact same command later (after fixing the board)
    picks up from where it stopped instead of re-running completed
    tests: this function loads that file itself, if present, and
    narrows the manifest to whatever isn't in it yet.

    Everything this invocation prints, including from any subprocess
    it spawns, is also written to <run_log.logs_dir>/real/latest.log
    (see run_log.start), a prior latest.log, if any, is archived
    under its own start timestamp first.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed `run` options: config, root, manifest (default
        <build_dir>/real/manifest.json), only and exclude (test names),
        skip_reconfigure, skip_recompile and wait_for_hardware (wait for
        the board instead of exiting with status 2).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout when the suite finishes,
        each line also shows the test's source language ("C"/"ASM"),
        kind ("unit"/"memory") and, for memory-kind tests, whether
        their golden.json came from Spike at this same compile (a .c
        test; see cli.generate_c_golden) or is checked into the
        repo (a .S test). Deletes run_progress.json, since there's
        nothing left to resume. Exits the process with status 1 if the
        manifest file
        is missing, if --only/--exclude names a test that isn't in
        the manifest or selects no tests, or if any completed test
        failed; status 2 if the suite stopped early for human
        intervention
        (run_progress.json is left in place in that case, specifically
        so a re-run finds
        it).
    """
    cfg, root, build_dir, manifest_path, manifest = start_real_run(
        args, "real"
    )
    # Kept separate from `manifest` itself, which gets filtered down
    # below (by --only, then again by whatever's already in
    # results_so_far); the summary at the end still needs every
    # requested test's own kind/golden info, including ones this
    # particular invocation never touched.
    manifest_by_name = {entry["name"]: entry for entry in manifest}

    manifest = _select_run_manifest(cfg, args, manifest, manifest_path)
    requested_names = {entry["name"] for entry in manifest}
    results_path = build_dir / "run_progress.json"
    results_so_far = _load_progress(results_path, requested_names)
    manifest = [e for e in manifest if e["name"] not in results_so_far]

    link = jtag_link(cfg)
    print(f"JTAG hardware: {link.hardware_name}")

    durations: dict[str, float] = {}
    if not manifest:
        # Every requested test was already in results_so_far.
        results = results_so_far
    else:
        results = orchestrator.run_suite(
            RunContext(
                cfg=cfg,
                link=link,
                build_dir=build_dir,
                root=root,
                project_dir=root / cfg["quartus"]["project_dir"],
            ),
            manifest,
            SuiteOptions(
                reconfigure=not args.skip_reconfigure,
                results_path=results_path,
                results_so_far=results_so_far,
                wait_for_hardware=args.wait_for_hardware,
                durations=durations,
                skip_recompile=args.skip_recompile,
            ),
        )

    print_run_summary(results, manifest_by_name, durations, root, build_dir)

    if len(results) < len(requested_names):
        print(
            f"\nStopped early: {len(results)}/{len(requested_names)} test(s) "
            f"done. Re-run this exact command after fixing the board to "
            "resume."
        )
        sys.exit(2)

    results_path.unlink(missing_ok=True)
    if not all(results.values()):
        sys.exit(1)


def cmd_sim(args: argparse.Namespace) -> None:
    """Implement `riscv-tools sim`.

    Runs a simulation test suite under cocotb/GHDL from a manifest.json
    (see sim_runner.run_suite). Runs every entry by default, with
    --only/--exclude available for DUT-specific subsets. Requires the
    "sim" extra (cocotb) to be installed.

    Everything this invocation prints, including GHDL/cocotb's own
    output, is also written to <run_log.logs_dir>/sim/latest.log (see
    run_log.start), a prior latest.log, if any, is archived under its
    own start timestamp first.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.root,
        args.manifest (defaults to <build_dir>/sim/manifest.json if
        not given), args.only and args.exclude (repeatable,
        comma-separated test-name filters).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if the manifest file is missing, a filter names an
        unknown test, no tests remain selected, or any test failed.
    """
    cfg, root = start_run(args, "sim")
    build_dir = root / cfg["paths"]["build_dir"] / "sim"
    # sim.image "mif" simulates the same images the hardware loads,
    # which `compile --emit mif` writes (and lists) under build/real.
    use_mif = cfg["sim"]["image"] == "mif"
    manifest_dir = (
        root / cfg["paths"]["build_dir"] / ("real" if use_mif else "sim")
    )
    manifest_path, manifest = load_manifest(
        args, manifest_dir, "mif" if use_mif else "hex"
    )
    manifest = filter_manifest(
        manifest,
        manifest_path,
        getattr(args, "only", []),
        getattr(args, "exclude", []),
    )

    # Built ONCE per invocation, reused across every manifest entry --
    # see boot_rom.build_boot_rom / sim_runner.run_suite's own
    # boot_rom_hex_path parameter. Only meaningful for a project whose
    # sim toplevel actually has a BOOT_ROM/FLASH split (paths.boot_rom
    # set) -- skipped otherwise.
    boot_rom_hex_path = None
    boot_rom_mif_path = None
    if cfg.get("paths", {}).get("boot_rom"):
        boot_rom_dir = build_dir / "boot_rom"
        boot_rom_hex_path = boot_rom.build_boot_rom(
            cfg["toolchain"],
            cfg["paths"],
            root,
            boot_rom_dir,
            hex_format=cfg["sim"]["hex_format"],
        )
        if use_mif:
            boot_rom_mif_path = boot_rom_dir / "boot_rom.mif"
            bin_to_image.bin_to_mif(
                boot_rom_dir / "boot_rom.bin",
                boot_rom_mif_path,
                depth=cfg["memory"]["boot_rom_words"],
            )

    results = sim_runner.run_suite(
        cfg,
        manifest,
        root,
        build_dir / "sim_work",
        boot_rom_hex_path=boot_rom_hex_path,
        boot_rom_mif_path=boot_rom_mif_path,
    )

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        sys.exit(1)
