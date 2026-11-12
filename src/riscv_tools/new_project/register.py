"""List the new platform where the repository keeps its platforms."""

import re
from pathlib import Path

from riscv_tools.new_project.template import Template, rename_text, snake

PATHS_FILE = "paths.yaml"
SOURCES_SCRIPT = "scripts/generate_sources.py"
_TOP_LEVEL = re.compile(r"^\S")
_COMPONENT = re.compile(r"^  \S")


def _block(lines: list[str], key: str) -> tuple[int, int]:
    """Find a component of `paths.yaml`.

    Parameters
    ----------
    lines : list of str
        The lines of the file.
    key : str
        Name of the component.

    Returns
    -------
    tuple of (int, int)
        Index of its first line and of the line after its last.

    Raises
    ------
    ValueError
        If the file has no such component.
    """
    start = next(
        (i for i, line in enumerate(lines) if line == f"  {key}:\n"), None
    )
    if start is None:
        raise ValueError(f"{PATHS_FILE} has no component {key}")
    end = start + 1
    while end < len(lines) and not (
        _COMPONENT.match(lines[end]) or _TOP_LEVEL.match(lines[end])
    ):
        end += 1
    return start, end


def register_paths(text: str, template: Template, new: str) -> str:
    """Add the new platform to the text of `paths.yaml`.

    The platform joins the list of platforms, and copies of the three
    components of the template (the map, the board top and the
    simulation top) follow the originals under the new names.

    Parameters
    ----------
    text : str
        The text of `paths.yaml`.
    template : Template
        The platform the new one was copied from.
    new : str
        Name of the new platform.

    Returns
    -------
    str
        The text with the new platform listed.

    Raises
    ------
    ValueError
        If the list of platforms or a component is missing.
    """
    old_us = snake(template.name)
    old_file = f"{template.folder.as_posix()}/platform.yaml"
    new_file = f"{template.folder.parent.as_posix()}/{new}/platform.yaml"
    pattern = rf"^(  - \{{name: platforms, paths: \[.*?){re.escape(old_file)}"
    text, count = re.subn(
        pattern,
        lambda m: f"{m[1]}{old_file}, {new_file}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError(f"{PATHS_FILE} does not list the platforms")
    lines = text.splitlines(keepends=True)
    board = template.top.removeprefix("Insper-RISC-V/")
    for key in (f"{old_us}_sim_top", board, f"{old_us}_map"):
        start, end = _block(lines, key)
        copy = rename_text(
            "".join(lines[start:end]), template.name, new, template.board
        )
        lines[end:end] = copy.splitlines(keepends=True)
    return "".join(lines)


def register_sources(text: str, template: Template, new: str) -> str | None:
    """Add the new configuration to the script of source lists.

    Parameters
    ----------
    text : str
        The text of `scripts/generate_sources.py`.
    template : Template
        The platform the new one was copied from.
    new : str
        Name of the new platform.

    Returns
    -------
    str or None
        The text with a copy of the template's line, or None when the
        script has no such line.
    """
    old_us = snake(template.name)
    line = (
        rf'^(\s*)Saida\(\s*"{re.escape(template.folder.as_posix())}'
        rf'/config\.yaml",\s*\("{old_us}_sim_top",\)\s*\),\n'
    )
    found = re.search(line, text, flags=re.MULTILINE)
    if found is None:
        return None
    copy = rename_text(found[0], template.name, new, template.board)
    return text[: found.end()] + copy + text[found.end() :]


def registration_edits(
    repo: Path, template: Template, new: str
) -> tuple[dict[Path, str], bool]:
    """Work out the edits that register the new platform.

    Nothing is written, so a repository whose files do not have the
    shape the edits need is left as it was.

    Parameters
    ----------
    repo : Path
        Root of the `Insper-RISC-V` checkout.
    template : Template
        The platform the new one was copied from.
    new : str
        Name of the new platform.

    Returns
    -------
    tuple of (dict of {Path: str}, bool)
        The new text of each file to change, and whether the script of
        source lists is among them (False when it has no line to copy
        and the person must add one).
    """
    paths = repo / PATHS_FILE
    edits = {paths: register_paths(paths.read_text(), template, new)}
    script = repo / SOURCES_SCRIPT
    if not script.is_file():
        return edits, False
    edited = register_sources(script.read_text(), template, new)
    if edited is None:
        return edits, False
    edits[script] = edited
    return edits, True
