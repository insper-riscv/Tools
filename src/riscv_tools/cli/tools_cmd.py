"""The subcommands that only read files or run small tools."""

import argparse
import json
import sys
from pathlib import Path

from riscv_tools import (
    memory_map,
    orchestrator,
    path_check,
    profiles,
    vhdl_sort,
)
from riscv_tools import timing_paths as timing_paths_mod
from riscv_tools.cli.common import jtag_link, project_root
from riscv_tools.orchestrator.sweep import SweepJob
from riscv_tools.settings import load_config


def cmd_vhdl_sort(args: argparse.Namespace) -> None:
    """Implement `riscv-tools vhdl-sort`.

    Prints args.files reordered so each file's VHDL entity/package
    dependencies precede it (see vhdl_sort.topo_sort) — for feeding
    GHDL's `-a` (analyze) phase, or a Makefile's `$(shell ...)`.
    Doesn't touch args.config; this subcommand needs no project
    config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.files.

    Returns
    -------
    None
        Prints the reordered file paths, space-separated, to stdout.
    """
    ordered = vhdl_sort.topo_sort([Path(f) for f in args.files])
    print(" ".join(str(f) for f in ordered))


def cmd_check_paths(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-paths`.

    Fails when a file path listed in the project's configuration does
    not exist (see path_check.check_paths). Doesn't touch args.config:
    the
    manifest lists the references to read.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.manifest and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 on any
        problem.
    """
    root = project_root(args)
    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = root / manifest
    count, problems = path_check.check_paths(manifest, root)
    if problems:
        for problem in problems:
            print(f"PATH {problem}", file=sys.stderr)
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        sys.exit(1)
    print(f"paths OK: {count} paths from {manifest.name}")


def cmd_profiles(args: argparse.Namespace) -> None:
    """Implement `riscv-tools profiles`.

    Prints every valid combination of the extensions of a profile
    specification (see profiles.expand). Doesn't touch args.config: the
    specification lists
    the extensions and the rules between them.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.spec and args.format.

    Returns
    -------
    None
        Prints one line per profile, or one JSON list.
    """
    found = profiles.expand(profiles.load_spec(Path(args.spec)))
    formatters = {"json": _profiles_json, "generics": _profiles_generics}
    for line in formatters.get(args.format, _profiles_names)(found):
        print(line)


def _profiles_json(found: list[profiles.Profile]) -> list[str]:
    """Format profiles as one JSON list.

    Parameters
    ----------
    found : list of Profile
        The profiles.

    Returns
    -------
    list of str
        One line holding the JSON text.
    """
    return [
        json.dumps(
            [
                {
                    "name": p.name,
                    "extensions": list(p.extensions),
                    "generics": dict(p.generics),
                }
                for p in found
            ],
            indent=2,
        )
    ]


def _profiles_generics(found: list[profiles.Profile]) -> list[str]:
    """Format profiles as a name and its GHDL `-g` flags per line.

    Parameters
    ----------
    found : list of Profile
        The profiles.

    Returns
    -------
    list of str
        One line per profile.
    """
    return [
        f"{p.name} "
        + " ".join(f"-g{k}={str(v).lower()}" for k, v in p.generics.items())
        for p in found
    ]


def _profiles_names(found: list[profiles.Profile]) -> list[str]:
    """Format profiles as one name per line.

    Parameters
    ----------
    found : list of Profile
        The profiles.

    Returns
    -------
    list of str
        One line per profile.
    """
    return [p.name for p in found]


def cmd_check_memory_map(args: argparse.Namespace) -> None:
    """Implement `riscv-tools check-memory-map`.

    Checks every copy of a platform's memory map against the platform's
    YAML (see memory_map.check_memory_map). Doesn't touch args.config:
    the
    platform file lists the copies to read.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.platform and args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 on any
        disagreement.
    """
    root = project_root(args)
    platform = Path(args.platform)
    if not platform.is_absolute():
        platform = root / platform
    count, problems = memory_map.check_memory_map(platform, root)
    if problems:
        for problem in problems:
            print(f"MISMATCH {problem}", file=sys.stderr)
        print(f"{len(problems)} disagreement(s)", file=sys.stderr)
        sys.exit(1)
    print(f"memory map OK: {count} checks against {platform.name}")


def cmd_timing_paths(args: argparse.Namespace) -> None:
    """Implement `riscv-tools timing-paths`.

    Runs the Timing Analyzer on the compiled project and prints the
    worst setup paths of every clock domain, the bits of a register
    folded into one
    row.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: args.config, args.root, args.npaths,
        args.model and args.out (optional file for the table).

    Returns
    -------
    None
        Prints the table, and writes it to args.out when given.
    """
    cfg = load_config(args.config)
    root = project_root(args)
    paths = timing_paths_mod.run_timing_paths(
        root / cfg["quartus"]["project_dir"],
        cfg["quartus"]["project_name"],
        args.npaths,
        args.model,
    )
    table = timing_paths_mod.format_table(timing_paths_mod.group_paths(paths))
    if args.out:
        Path(args.out).write_text(table, encoding="utf-8")
    print(table, end="")


def cmd_freq_sweep(args: argparse.Namespace) -> None:
    """Implement `riscv-tools freq-sweep`.

    Finds the board's Fmax for a fixed test program by sweeping (or
    binary-searching) candidate clock frequencies, editing the
    project's PLL and doing a full recompile+reprogram+RAM-compare at
    each one (see orchestrator.run_freq_sweep_linear/
    run_freq_sweep_binary).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root, args.mif,
        args.golden, args.binary, args.start/args.stop/args.step
        (linear mode), args.low/args.high (binary mode), args.out
        (results JSON path; default
        <build_dir>/freq_sweep/freq_sweep_results.json).

    Returns
    -------
    None
        Writes results to args.out and prints a summary. Exits the
        process with status 1 if no candidate frequency passed.
    """
    cfg = load_config(args.config)
    root = project_root(args)
    link = jtag_link(cfg)
    project_dir = root / cfg["quartus"]["project_dir"]
    build_dir = root / cfg["paths"]["build_dir"] / "freq_sweep"
    build_dir.mkdir(parents=True, exist_ok=True)
    # documented as relative to the project root, not to the cwd
    cfg["freq_sweep"]["pll_file"] = str(root / cfg["freq_sweep"]["pll_file"])

    job = SweepJob(
        cfg=cfg,
        link=link,
        mif_path=Path(args.mif),
        golden_path=Path(args.golden),
        project_dir=project_dir,
        build_dir=build_dir,
    )

    if args.binary:
        results = orchestrator.run_freq_sweep_binary(job, args.low, args.high)
    else:
        results = orchestrator.run_freq_sweep_linear(
            job, args.start, args.stop, args.step
        )

    out_path = (
        Path(args.out) if args.out else build_dir / "freq_sweep_results.json"
    )
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['freq_mhz']:>8} MHz : {r['status']}")

    passes = [r["freq_mhz"] for r in results if r["status"] == "pass"]
    if passes:
        print(f"Highest passing frequency: {max(passes)} MHz")
    else:
        print("No candidate frequency passed", file=sys.stderr)
        sys.exit(1)
