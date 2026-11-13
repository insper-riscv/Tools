"""The commands a project runs, built from its manifest."""

import sys
from pathlib import Path

from riscv_tools.project.manifest import Manifest

STOP_AFTER = ("map", "fit", "sta")
TESTS_FOLDER = "Tests"
_MODULE = [sys.executable, "-m", "riscv_tools.cli"]


def _program(project: Path, manifest: Manifest, *args: str) -> list[str]:
    """Build a `program` command for the platform of the project.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        The project.
    *args : str
        Options and arguments of `program`.

    Returns
    -------
    list of str
        The command; run it with the checkout as the working folder.
    """
    return [
        *_MODULE,
        "--root",
        str(manifest.repo_path(project)),
        "--config",
        manifest.config_path(),
        "--board",
        manifest.board,
        "program",
        *args,
    ]


def build_command(
    project: Path, manifest: Manifest, stop_after: str
) -> list[str]:
    """Build the command that compiles the Quartus project.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        The project.
    stop_after : str
        The last Quartus step to run: `map`, `fit` or `sta`.

    Returns
    -------
    list of str
        The command; it does not program the board.

    Raises
    ------
    ValueError
        If `stop_after` is not a known step.
    """
    if stop_after not in STOP_AFTER:
        raise ValueError(
            f"--stop-after must be one of {', '.join(STOP_AFTER)}"
        )
    return _program(project, manifest, "--stop-after", stop_after)


def config_of_tests(project: Path, manifest: Manifest) -> Path:
    """Locate the config of the `Tests` repository for the platform.

    Programming the board with an image needs the build folder that
    only the configuration of `Tests` names, so `flash` runs on it.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        The project.

    Returns
    -------
    Path
        The `config.<slug>.yaml` under `Tests/tools/riscv_build`.
    """
    return (
        project
        / TESTS_FOLDER
        / "tools/riscv_build"
        / f"config.{manifest.slug}.yaml"
    )


def flash_command(project: Path, manifest: Manifest, image: Path) -> list[str]:
    """Build the command that programs the board with an image.

    The board is locked while it runs, waiting if someone else has it.
    The program runs on the configuration of `Tests`, which names the
    build folder the `.mif` is merged in.

    Parameters
    ----------
    project : Path
        The project folder.
    manifest : Manifest
        The project.
    image : Path
        The `.mif` of the program.

    Returns
    -------
    list of str
        The command; run it with `Tests` as the working folder.

    Raises
    ------
    FileNotFoundError
        If the `Tests` configuration of the platform does not exist
        yet.
    """
    config = config_of_tests(project, manifest)
    if not config.is_file():
        raise FileNotFoundError(
            f"{config} does not exist; prepare Tests first "
            "(`riscv-tools project help`, steps 1 to 3)"
        )
    return [
        *_MODULE,
        "board",
        "lock",
        "--board",
        manifest.board,
        "--wait",
        "--",
        *_MODULE,
        "--root",
        str(project / TESTS_FOLDER),
        "--config",
        str(config),
        "--board",
        manifest.board,
        "program",
        str(image.resolve()),
    ]
