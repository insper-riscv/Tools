"""The `spike-run` subcommand."""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from riscv_tools import (
    spike_run,
)
from riscv_tools.cli.common import start_real_run
from riscv_tools.cli.project import discover_tests, spike_elf, spike_target


def print_run_summary(
    results: dict[str, bool],
    manifest_by_name: dict[str, dict[str, Any]],
    durations: dict[str, float],
    root: Path,
    build_dir: Path,
) -> None:
    """Print the final table of cmd_run.

    Each row is ``PASS/FAIL  name  [lang, kind, golden: ..., Ns]``.
    """
    print("\n=== Summary ===")
    name_width = max((len(name) for name in results), default=0)
    for name, ok in results.items():
        entry = manifest_by_name.get(name, {})
        kind = entry.get("kind", "?")
        lang = entry.get("lang", "?")
        detail = f"{lang}, {kind}"
        if kind == "memory" and "golden" in entry:
            # Same test/repo distinction as generate_c_golden's own
            # ephemeral build/real/<name>.golden.json vs an asm test's
            # checked-in <test_dir>/golden.json, whichever one this
            # test's golden path actually resolves under.
            golden_path = root / entry["golden"]
            origin = (
                "spike"
                if golden_path.is_relative_to(build_dir)
                else "checked-in"
            )
            detail = f"{lang}, {kind}, golden: {origin}"
        if name in durations:
            detail = f"{detail}, {durations[name]:.1f}s"
        print(
            f"  {'PASS' if ok else 'FAIL'}  {name:<{name_width}}  [{detail}]"
        )


def _wanted_names(
    only: str | None,
    by_name: dict[str, dict[str, Any]],
    manifest_path: Path,
) -> list[str]:
    """Resolve the tests `spike-run` should run.

    Parameters
    ----------
    only : str or None
        Comma-separated test names, or None/empty for all.
    by_name : dict of {str: dict of {str: Any}}
        The manifest entries by name.
    manifest_path : Path
        Path used in error diagnostics.

    Returns
    -------
    list of str
        The names to run. Exits with status 1 on an unknown name.
    """
    wanted = [n for n in (only or "").split(",") if n] or list(by_name)
    unknown = [n for n in wanted if n not in by_name]
    if unknown:
        print(f"not in {manifest_path}: {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)
    return wanted


def _print_failure_output(result: spike_run.SpikeRunResult) -> None:
    """Print the Spike output of a failed run.

    Parameters
    ----------
    result : spike_run.SpikeRunResult
        The run outcome.
    """
    if not result.passed and result.output:
        print(result.output.rstrip())


def _spike_run_all(
    cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    by_name: dict[str, dict[str, Any]],
    wanted: list[str],
) -> tuple[dict[str, bool], dict[str, float]]:
    """Run the wanted tests under Spike and time each one.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The loaded config.yaml.
    root : Path
        The consuming project's root.
    build_dir : Path
        The real build directory (holds the ELFs).
    by_name : dict of {str: dict of {str: Any}}
        The manifest entries by test name.
    wanted : list of str
        The names to run, in order.

    Returns
    -------
    tuple of dict
        Whether each test passed, and how long each took in seconds.
    """
    sources = {src.parent.name: src for src in discover_tests(root, cfg)}
    emulator = cfg["emulator"]
    results: dict[str, bool] = {}
    durations: dict[str, float] = {}
    for name in wanted:
        entry = by_name[name]
        print(f"Running {name} under Spike ...")
        started = time.monotonic()
        result = spike_run.run_elf(
            spike_target(cfg, entry["march"], emulator["entry_symbol"]),
            spike_elf(cfg, name, build_dir, root, sources[name]),
            timeout_s=entry.get("timeout_s", emulator["timeout_s"]),
        )
        durations[name] = time.monotonic() - started
        results[name] = result.passed
        _print_failure_output(result)
    return results, durations


def cmd_spike_run(args: argparse.Namespace) -> None:
    """Implement `riscv-tools spike-run`.

    Runs every test of an already-compiled manifest to completion under
    Spike and reports PASS/FAIL from the HTIF verdict each test writes
    to tohost, without touching hardware or a simulator. Everything this
    invocation prints is also written to
    <run_log.logs_dir>/spike/latest.log (see run_log.start).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: args.config, args.root, args.manifest
        (defaults to <build_dir>/real/manifest.json) and args.only
        (comma-separated test names to run, default all).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if the manifest is missing, a requested test isn't in
        it, or any test failed.
    """
    cfg, root, build_dir, manifest_path, manifest = start_real_run(
        args, "spike"
    )
    by_name = {entry["name"]: entry for entry in manifest}
    wanted = _wanted_names(args.only, by_name, manifest_path)

    results, durations = _spike_run_all(cfg, root, build_dir, by_name, wanted)

    print_run_summary(results, by_name, durations, root, build_dir)
    if not all(results.values()):
        sys.exit(1)
