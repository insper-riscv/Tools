"""Run the VSG over the VHDL files of a repository.

The configuration (`vsg.yaml`), the layer for the board
(`vsg-board.yaml`) and the local rules are data of this package. The
VSG runs in the environment of `riscv-tools`, once for the sources and
once for the top-levels of the board, which skip the naming rules.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.vhdl_style.files import vhdl_files

_HERE = Path(__file__).parent
CONFIG = _HERE / "vsg.yaml"
BOARD_CONFIG = _HERE / "vsg-board.yaml"
LOCAL_RULES = _HERE / "local_rules"
_ENTRY = "from vsg.__main__ import main; main()"

# What the CI gate demands today, the checks the former parser of
# `check-vhdl-style` made; `--full` runs every rule of `vsg.yaml`.
GATE_RULES = (
    "header_900",
    "library_900",
    "component_900",
    "port_map_900",
    "docstring_900",
    "port_600",
    "port_601",
    "port_602",
    "constant_004",
    "type_600",
    "subtype_600",
    "instantiation_601",
)


def _load(path: Path) -> dict[str, Any]:
    """Read a YAML file into a mapping.

    Parameters
    ----------
    path : Path
        The file.

    Returns
    -------
    dict of str to Any
        The content of the file.
    """
    return cast("dict[str, Any]", yaml.safe_load(path.read_text("utf-8")))


def _gate_config(base: dict[str, Any]) -> dict[str, Any]:
    """Keep only the gate rules enabled in a configuration.

    Parameters
    ----------
    base : dict of str to Any
        The content of `vsg.yaml`.

    Returns
    -------
    dict of str to Any
        The same configuration with every rule disabled but the ones in
        `GATE_RULES`, which keep their options.
    """
    rules = cast("dict[str, Any]", base["rule"])
    rules["global"]["disable"] = True
    for name, options in rules.items():
        if name != "global" and name not in GATE_RULES:
            options["disable"] = True
    for name in GATE_RULES:
        rules.setdefault(name, {})["disable"] = False
    return base


def _write_config(full: bool, board: bool, folder: Path) -> Path:
    """Write the configuration of a run to a temporary file.

    Parameters
    ----------
    full : bool
        True for every rule of `vsg.yaml`, False for the gate rules.
    board : bool
        True to turn off the naming rules, for the board.
    folder : Path
        The folder that holds the file.

    Returns
    -------
    Path
        The file, to give to `vsg -c`.
    """
    config = _load(CONFIG)
    if not full:
        config = _gate_config(config)
    if board:
        cast("dict[str, Any]", config["rule"]).update(
            _load(BOARD_CONFIG)["rule"]
        )
    path = folder / f"vsg-{'board' if board else 'src'}.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), "utf-8")
    return path


def _run_group(
    root: Path, config: Path, files: list[str], output_format: str
) -> subprocess.CompletedProcess[str]:
    """Run the VSG over a list of files.

    Parameters
    ----------
    root : Path
        The repository root, where the VSG runs.
    config : Path
        The configuration file.
    files : list of str
        The files, relative to the root.
    output_format : str
        The `-of` format of the VSG.

    Returns
    -------
    subprocess.CompletedProcess of str
        The finished process, with its output captured.
    """
    command = [
        sys.executable,
        "-c",
        _ENTRY,
        "-c",
        str(config),
        "-lr",
        str(LOCAL_RULES),
        "-ap",
        "-of",
        output_format,
        "-f",
        *files,
    ]
    return subprocess.run(
        command, cwd=root, capture_output=True, text=True, check=False
    )


def run_vsg(
    root: Path, full: bool = False, output_format: str = "vsg"
) -> tuple[int, str]:
    """Run the VSG over the VHDL files of a repository.

    Parameters
    ----------
    root : Path
        The repository root.
    full : bool, optional
        True to apply every rule of `vsg.yaml`, False for the rules the
        CI gate demands today, by default False.
    output_format : str, optional
        The `-of` format of the VSG, by default `vsg`.

    Returns
    -------
    tuple of int and str
        The status (0 when no file has a violation) and the output of
        the VSG.
    """
    status = 0
    output: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for board in (False, True):
            files = vhdl_files(root, board)
            if not files:
                continue
            config = _write_config(full, board, Path(scratch))
            done = _run_group(root, config, files, output_format)
            status = status or done.returncode
            output.append(done.stdout + done.stderr)
    return status, "".join(output)
