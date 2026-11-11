"""The subcommand that creates a project for a known board."""

import argparse
import subprocess
import sys
from pathlib import Path

from riscv_tools import memory_map, new_project
from riscv_tools.new_project import ProjectSpec
from riscv_tools.project import Manifest, write_launcher, write_manifest


def _spec(args: argparse.Namespace) -> ProjectSpec:
    """Read the choices of the project off the command line.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.name, args.project_board,
        args.project_profile, args.rom, args.ram, args.icache and
        args.dcache.

    Returns
    -------
    ProjectSpec
        The choices; a memory option that was not given stays None.

    Raises
    ------
    ValueError
        If a size or a cache is malformed.
    """
    return ProjectSpec(
        name=args.name,
        board=args.project_board,
        profile=args.project_profile,
        rom_bytes=None
        if args.rom is None
        else new_project.parse_size(args.rom),
        ram_bytes=None
        if args.ram is None
        else new_project.parse_size(args.ram),
        icache_bits=(
            None
            if args.icache is None
            else new_project.parse_cache(args.icache)
        ),
        dcache_bits=(
            None
            if args.dcache is None
            else new_project.parse_cache(args.dcache)
        ),
    )


def _checkout(args: argparse.Namespace) -> tuple[Path, Path]:
    """Get the folder of the project and the checkout in it.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.repo, args.dir, args.name and
        args.source.

    Returns
    -------
    tuple of (Path, Path)
        The folder of the project and the `Insper-RISC-V` checkout:
        the one `--repo` names, or a new clone under `--dir`.
    """
    if args.repo:
        repo = Path(args.repo).resolve()
        return repo.parent, repo
    project = Path(args.dir).resolve() / args.name
    repo = project / new_project.REPO_FOLDER
    new_project.clone(args.source, repo)
    return project, repo


def cmd_new_project(args: argparse.Namespace) -> None:
    """Implement `riscv-tools new-project`.

    Downloads the `Insper-RISC-V` repository (or takes the checkout of
    `--repo`), copies the platform of the board under the new name,
    writes its `platform.yaml` from the choices, lists it in the
    repository, generates the files that follow from it and prints a
    short help. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.name, args.project_board,
        args.project_profile, args.rom, args.ram, args.icache,
        args.dcache, args.dir, args.source, args.repo,
        args.no_generate and args.lang.

    Returns
    -------
    None
        Prints the help; exits the process with status 1 when a choice
        is not accepted, the download fails or a generation step
        fails.
    """
    try:
        spec = _spec(args)
        new_project.validate(
            spec,
            [spec.board],
            [spec.profile] if spec.profile else [],
        )
        project, repo = _checkout(args)
        created = new_project.create_platform(repo, spec)
        if not args.no_generate:
            new_project.run_steps(
                repo,
                new_project.generation_steps(repo, created, spec.board),
            )
        write_manifest(
            project,
            Manifest(
                spec.name, spec.board, repo.name, created.folder.as_posix()
            ),
        )
        write_launcher(project)
    except (
        ValueError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"new-project: {error}", file=sys.stderr)
        sys.exit(1)
    if not created.script_edited:
        print(
            "NOTE scripts/generate_sources.py has no line to copy: add the "
            f"{created.folder}/config.yaml entry by hand",
            file=sys.stderr,
        )
    platform = memory_map.load_platform(repo / created.platform)
    print(
        new_project.render_help(
            args.lang,
            new_project.Summary(
                project,
                repo,
                created.folder,
                created.template.name,
                spec.board,
                platform,
            ),
        )
    )
