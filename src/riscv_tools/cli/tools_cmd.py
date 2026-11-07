"""The subcommands that only read files or run small tools."""

import argparse
import json
import sys
from pathlib import Path

from riscv_tools import (
    board_check,
    memory_map,
    path_check,
    profiles,
    vhdl_sort,
)
from riscv_tools import timing_paths as timing_paths_mod
from riscv_tools.cli.common import project_root
from riscv_tools.settings import load_config


def cmd_vhdl_sort(args: argparse.Namespace) -> None:
    """Implement `riscv-tools vhdl-sort`.

    Prints args.files reordered so each file's entity and package
    dependencies come first, for GHDL's analyze phase or a Makefile's
    `$(shell ...)`. It needs no project config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.files.

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
        Parsed CLI arguments: uses args.manifest and args.root.

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
        Parsed CLI arguments: uses args.spec and args.format.

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
        Parsed CLI arguments: uses args.platform and args.root.

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
    findings = board_check.check_platform_file(
        platform, root, accept_inferred_pins=args.accept_inferred_pins
    )
    errors = [f for f in findings if f.level == "E"]
    for problem in problems:
        print(f"MISMATCH {problem}", file=sys.stderr)
    for finding in findings:
        print(f"BOARD {finding.rule} {finding}", file=sys.stderr)
    if problems or errors:
        total = len(problems) + len(errors)
        print(f"{total} disagreement(s)", file=sys.stderr)
        sys.exit(1)
    print(f"memory map OK: {count} checks against {platform.name}")


def cmd_generate_memory_map(args: argparse.Namespace) -> None:
    """Implement `riscv-tools generate-memory-map`.

    Writes the files the platform YAML asks for under `generate` (the
    linker flags, the linker script of the boot memory and the VHDL
    package of the map), or with `--check` only compares them with
    what is on disk.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.platform, args.check and
        args.root.

    Returns
    -------
    None
        Prints the result; exits the process with status 1 when a file
        is out of date in `--check` or the map is inconsistent.
    """
    root = project_root(args)
    platform = Path(args.platform)
    if not platform.is_absolute():
        platform = root / platform
    try:
        for note in memory_map.memory_notes(
            memory_map.load_platform(platform)
        ):
            print(f"NOTE {note}", file=sys.stderr)
        if args.check:
            count, problems = memory_map.check_all(platform, root)
            if problems:
                for problem in problems:
                    print(f"MISMATCH {problem}", file=sys.stderr)
                sys.exit(1)
            print(f"generated files OK: {count} from {platform.name}")
            return
        written = memory_map.write_all(platform, root)
    except ValueError as error:
        print(f"ERROR {error}", file=sys.stderr)
        sys.exit(1)
    for path in written:
        print(f"generated: {path.relative_to(root)}")


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
