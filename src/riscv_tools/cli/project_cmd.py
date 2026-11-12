"""The subcommand that works on a project made by `new-project`."""

import argparse
import subprocess
import sys
from pathlib import Path

from riscv_tools import memory_map, project


def _find(args: argparse.Namespace) -> tuple[Path, project.Manifest]:
    """Find the project the command works on.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.dir.

    Returns
    -------
    tuple of (Path, Manifest)
        The project folder and its manifest; exits with status 1 when
        there is none.
    """
    try:
        return project.find_manifest(Path(args.dir).resolve())
    except (FileNotFoundError, ValueError) as error:
        print(f"project: {error}", file=sys.stderr)
        sys.exit(1)


def _run(command: list[str], cwd: Path) -> None:
    """Run a command and exit with its status when it fails.

    Parameters
    ----------
    command : list of str
        The command.
    cwd : Path
        The working folder.
    """
    print("+", " ".join(command), flush=True)
    status = subprocess.run(command, cwd=cwd, check=False).returncode
    if status:
        sys.exit(status)


def _flash(folder: Path, manifest: project.Manifest, image: Path) -> None:
    """Program the board with an image, from the `Tests` folder.

    Parameters
    ----------
    folder : Path
        The project folder.
    manifest : Manifest
        The project.
    image : Path
        The `.mif` of the program.
    """
    try:
        command = project.flash_command(folder, manifest, image)
    except FileNotFoundError as error:
        print(f"project: {error}", file=sys.stderr)
        sys.exit(1)
    _run(command, folder / project.TESTS_FOLDER)


def _doctor(folder: Path, manifest: project.Manifest) -> None:
    """Print the checks of the project and exit 1 if one fails.

    Parameters
    ----------
    folder : Path
        The project folder.
    manifest : Manifest
        The project.
    """
    checks = [
        *project.check_files(folder, manifest),
        *project.check_quartus(),
        project.check_cable(
            idcode=project.board_idcode(
                manifest.repo_path(folder), manifest.board
            )
        ),
    ]
    print(project.render(checks))
    if not project.passed(checks):
        sys.exit(1)


def cmd_project(args: argparse.Namespace) -> None:
    """Implement `riscv-tools project`.

    Works on the project whose `project.yaml` is in `--dir` or above
    it: `build` compiles the Quartus project without programming the
    board, `flash` programs the board with an image while holding the
    lock of the board, `doctor` checks the files, the Quartus tools
    and the JTAG cable, and `help` prints how to run the tests and
    compile a program. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.action, args.target, args.dir,
        args.stop_after and args.lang.

    Returns
    -------
    None
        Exits the process with the status of the command that failed.
    """
    folder, manifest = _find(args)
    repo = manifest.repo_path(folder)
    if args.action == "doctor":
        _doctor(folder, manifest)
    elif args.action == "help":
        platform = memory_map.load_platform(
            repo / manifest.platform / "platform.yaml"
        )
        print(project.render_tests_help(args.lang, manifest, platform))
    elif args.action == "build":
        _run(project.build_command(folder, manifest, args.stop_after), repo)
    elif args.target is None or not Path(args.target).is_file():
        print("project: flash needs the .mif of a program", file=sys.stderr)
        sys.exit(1)
    else:
        _flash(folder, manifest, Path(args.target))
