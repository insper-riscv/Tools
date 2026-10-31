"""The worst timing paths of a compiled Quartus project, by register.

The Timing Analyzer reports paths one bit at a time (``r_alu_out[13]``).
This module asks it for the worst setup paths of every clock domain,
then folds the bits of a register into one row, so the critical path
reads as "from this register to that one" and a stage that dominates
shows up at once. Pure mechanism, no policy.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TCL_FILE = Path(__file__).parent / "tcl" / "paths.tcl"
PATH_PREFIX = "PATH\t"
FIELDS = 6
PIPELINE_STAGES = {
    "reg_if_id": "IF/ID",
    "reg_id_ex": "ID/EX",
    "reg_ex_mem": "EX/MEM",
    "reg_mem_wb": "MEM/WB",
}
_BIT_INDEX = re.compile(r"\[\d+\]$")
_INSTANCE_NAME = re.compile(r"^[\w.$]+:([\w.$\[\]]+)$")


@dataclass(frozen=True)
class TimingPath:
    """One setup path as the Timing Analyzer reports it.

    Parameters
    ----------
    clock : str
        Clock of the destination register.
    slack : float
        Setup slack in ns (negative fails).
    delay : float
        Data path delay in ns.
    source : str
        Hierarchical name of the source node.
    destination : str
        Hierarchical name of the destination node.
    """

    clock: str
    slack: float
    delay: float
    source: str
    destination: str


@dataclass(frozen=True)
class PathGroup:
    """The paths sharing a clock, a source and a destination register.

    Parameters
    ----------
    clock : str
        Clock of the destination registers.
    source : str
        Source register without the bit index, with its pipeline stage.
    destination : str
        Destination register without the bit index, with its pipeline
        stage.
    paths : int
        How many bits of the pair appear among the reported paths.
    slack : float
        Worst slack of the group in ns.
    delay : float
        Longest data delay of the group in ns.
    """

    clock: str
    source: str
    destination: str
    paths: int
    slack: float
    delay: float


def parse_paths(output: str) -> list[TimingPath]:
    """Read the path lines out of the output of ``paths.tcl``.

    Parameters
    ----------
    output : str
        Everything the script printed.

    Returns
    -------
    list of TimingPath
        The paths in the order the script printed them.

    Raises
    ------
    ValueError
        A path line does not have the expected fields.
    """
    paths: list[TimingPath] = []
    for line in output.splitlines():
        if not line.startswith(PATH_PREFIX):
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) != FIELDS:
            raise ValueError(f"malformed path line: {line!r}")
        _, clock, slack, delay, source, destination = fields
        paths.append(
            TimingPath(clock, float(slack), float(delay), source, destination)
        )
    return paths


def register_of(node: str) -> str:
    """Name a node as its register and the pipeline stage it belongs to.

    Parameters
    ----------
    node : str
        Hierarchical node name, such as
        ``core:CORE|reg_mem_wb:u_reg_mem_wb|r_x[3]``.

    Returns
    -------
    str
        The node without the bit index, with the stage in front when it
        sits in a pipeline register (``MEM/WB r_x``), or the path below
        the top otherwise.
    """
    parts = _BIT_INDEX.sub("", node).split("|")
    name = parts[-1]
    for part in parts[:-1]:
        entity = part.split(":", 1)[0]
        if entity in PIPELINE_STAGES:
            return f"{PIPELINE_STAGES[entity]} {name}"
    trail = [_INSTANCE_NAME.sub(r"\1", part) for part in parts]
    return "|".join(trail[-3:])


def group_paths(paths: list[TimingPath]) -> list[PathGroup]:
    """Fold the bits of each register pair into one group.

    Parameters
    ----------
    paths : list of TimingPath
        The paths to fold.

    Returns
    -------
    list of PathGroup
        One group per clock, source register and destination register,
        the worst slack first.
    """
    groups: dict[tuple[str, str, str], list[TimingPath]] = {}
    for path in paths:
        key = (
            path.clock,
            register_of(path.source),
            register_of(path.destination),
        )
        groups.setdefault(key, []).append(path)
    rows = [
        PathGroup(
            clock=clock,
            source=source,
            destination=destination,
            paths=len(members),
            slack=min(m.slack for m in members),
            delay=max(m.delay for m in members),
        )
        for (clock, source, destination), members in groups.items()
    ]
    return sorted(rows, key=lambda row: (row.slack, row.clock, row.source))


def format_table(groups: list[PathGroup]) -> str:
    """Render the groups as a Markdown table.

    Parameters
    ----------
    groups : list of PathGroup
        The groups to show.

    Returns
    -------
    str
        The table, one row per group.
    """
    lines = [
        "| Clock | Source | Destination | Bits | Slack (ns) | Delay (ns) |",
        "| :--- | :--- | :--- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| `{g.clock}` | `{g.source}` | `{g.destination}` | {g.paths} "
        f"| {g.slack:.3f} | {g.delay:.3f} |"
        for g in groups
    )
    return "\n".join(lines) + "\n"


def run_timing_paths(
    project_dir: Path, project_name: str, npaths: int = 30, model: str = "slow"
) -> list[TimingPath]:
    """Run the Timing Analyzer on a compiled project; read worst paths.

    Parameters
    ----------
    project_dir : Path
        Directory of the Quartus project, where the compiled database
        lives.
    project_name : str
        Name of the project (the .qpf without the extension).
    npaths : int, optional
        Setup paths to ask for in each clock domain.
    model : str, optional
        ``slow`` (1100 mV, 85 C) or ``fast``.

    Returns
    -------
    list of TimingPath
        The paths of every domain.

    Raises
    ------
    RuntimeError
        The analyzer failed.
    """
    cmd = [
        "quartus_sta",
        "-t",
        str(TCL_FILE),
        project_name,
        str(npaths),
        model,
    ]
    done = subprocess.run(
        cmd, cwd=project_dir, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"quartus_sta failed ({done.returncode}): {done.stderr}"
        )
    return parse_paths(done.stdout)
