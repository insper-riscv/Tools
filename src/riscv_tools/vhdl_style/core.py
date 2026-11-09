"""Check the VHDL files of a repository against the style guide.

`check_vhdl_style` is a shortcut for the VSG: it runs it with the
configuration and the local rules of the project over the files that
`vhdl_files` lists, and returns what the VSG reports.
"""

from pathlib import Path

from riscv_tools.vhdl_style.runner import run_vsg


def check_vhdl_style(root: Path, full: bool = False) -> list[str]:
    """Run the VSG over the VHDL files of a repository.

    Parameters
    ----------
    root : Path
        The repository root.
    full : bool, optional
        True to apply every rule of `vsg.yaml`, False for the rules the
        CI gate demands today, by default False.

    Returns
    -------
    list of str
        One line for each violation, as the `syntastic` format of the
        VSG prints it; empty when every file conforms.
    """
    status, output = run_vsg(root, full, "syntastic")
    lines = [line for line in output.splitlines() if line.strip()]
    if status and not lines:
        lines = ["vsg failed without output"]
    return lines
