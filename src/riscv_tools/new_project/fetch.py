"""Download the repository a new project is built in."""

import subprocess
from pathlib import Path

DEFAULT_SOURCE = "https://github.com/insper-riscv/Insper-RISC-V.git"
REPO_FOLDER = "Insper-RISC-V"


def clone(url: str, target: Path) -> None:
    """Clone a repository with its submodules.

    Parameters
    ----------
    url : str
        Address of the repository (a URL or a local path).
    target : Path
        Folder to create.

    Raises
    ------
    FileExistsError
        If the folder already exists.
    subprocess.CalledProcessError
        If `git` fails.
    """
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--recurse-submodules",
            "--shallow-submodules",
            url,
            str(target),
        ],
        check=True,
    )
