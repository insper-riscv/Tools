"""Create the platform of a new project inside a checkout."""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.board_schema import Catalog
from riscv_tools.new_project.clone import copy_platform
from riscv_tools.new_project.platform_text import rewrite_platform
from riscv_tools.new_project.register import registration_edits
from riscv_tools.new_project.spec import ProjectSpec, validate
from riscv_tools.new_project.template import (
    TOP_PREFIX,
    Template,
    find_template,
    rename_text,
    snake,
)
from riscv_tools.profiles import expand, load_spec

MATRIX = "Core/profiles/matrix.yaml"
SOURCES_SCRIPT = "scripts/generate_sources.py"


@dataclass(frozen=True)
class Created:
    """What `create_platform` made.

    Parameters
    ----------
    template : Template
        The platform the new one was copied from.
    folder : Path
        Folder of the new platform, from the repository root.
    script_edited : bool
        True when `scripts/generate_sources.py` got a line for it.
    """

    template: Template
    folder: Path
    script_edited: bool

    @property
    def platform(self) -> Path:
        """The `platform.yaml` of the new platform."""
        return self.folder / "platform.yaml"


def check_boot_needs(
    repo: Path, template: Template, spec: ProjectSpec, names: list[str]
) -> None:
    """Refuse a profile the boot memory of the template cannot run on.

    The boot memory executes `fence.i`, which a core without Zifencei
    takes as an illegal instruction; the trap vector is address 0, so
    the boot would start over forever.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    template : Template
        The platform the new one is copied from.
    spec : ProjectSpec
        The choices of the project.
    names : list of str
        The names of the valid profiles.

    Raises
    ------
    ValueError
        If the profile lacks Zifencei while the boot memory needs it;
        the message names the profile that has it.
    """
    boot = repo / template.folder / "runtime" / "boot_memory.S"
    if spec.profile is None or not boot.is_file():
        return
    if "fence.i" not in boot.read_text():
        return
    tokens = set(spec.profile.split("_"))
    if "zifencei" in tokens:
        return
    fixed = next(
        (n for n in names if set(n.split("_")) == tokens | {"zifencei"}),
        f"{spec.profile}_zifencei",
    )
    raise ValueError(
        f"the boot memory of {template.name} executes fence.i, which a "
        f"core without Zifencei takes as an illegal instruction and the "
        f"boot restarts forever; use the profile {fixed}"
    )


def create_platform(repo: Path, spec: ProjectSpec) -> Created:
    """Copy, edit and register the platform of a project.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    spec : ProjectSpec
        The choices of the project.

    Returns
    -------
    Created
        The new platform.

    Raises
    ------
    ValueError
        If a choice is not accepted or the template has a shape the
        edits do not know; nothing is copied in the first case.
    FileExistsError
        If the platform already exists.
    """
    names = [p.name for p in expand(load_spec(repo / MATRIX))]
    validate(spec, Catalog.for_root(repo).board_names(), names)
    template = find_template(repo, spec.board)
    check_boot_needs(repo, template, spec, names)
    top = f"{TOP_PREFIX}{snake(spec.name)}_board"
    source = repo / template.folder / "platform.yaml"
    text = rewrite_platform(
        rename_text(
            source.read_text(encoding="utf-8"),
            template.name,
            spec.name,
            template.board,
        ),
        spec,
        template.name,
        top,
    )
    edits, edited = registration_edits(repo, template, spec.name)
    folder = copy_platform(repo, template, spec.name)
    (repo / folder / "platform.yaml").write_text(text, encoding="utf-8")
    for path, content in edits.items():
        path.write_text(content)
    return Created(template, folder, edited)


def generation_steps(
    repo: Path, created: Created, board: str
) -> list[tuple[str, list[str]]]:
    """List the commands that generate everything for the platform.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    created : Created
        The new platform.
    board : str
        The board of the project.

    Returns
    -------
    list of tuple of (str, list of str)
        A label and a command for each step, in the order they run.
    """
    tool = [sys.executable, "-m", "riscv_tools.cli", "--root", str(repo)]
    platform = str(created.platform)
    return [
        (
            "memory map",
            [*tool, "generate-memory-map", "--platform", platform],
        ),
        ("source lists", [sys.executable, SOURCES_SCRIPT]),
        (
            "memory map check",
            [*tool, "check-memory-map", "--platform", platform],
        ),
        (
            "Quartus project",
            [
                *tool,
                "--board",
                board,
                "board",
                "generate",
                "--platform",
                platform,
                "--out",
                "build",
            ],
        ),
    ]


def run_steps(repo: Path, steps: list[tuple[str, list[str]]]) -> None:
    """Run the generation steps, stopping at the first that fails.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout; the working folder.
    steps : list of tuple of (str, list of str)
        The labelled commands.

    Raises
    ------
    RuntimeError
        Naming the step that failed.
    """
    for label, command in steps:
        print(f"==> {label}", flush=True)
        done = subprocess.run(command, cwd=repo, check=False)
        if done.returncode:
            raise RuntimeError(f"step failed: {label}")
