"""Reduce a file that needs a vendor library to its entity declaration.

The simulation libraries of the FPGA vendor (`altera_mf`) come with
Quartus and are not in the toolchain image. A file that names one is
analyzed with only its entity declaration, which is all the component
needs: the lines that name the library are commented out and everything
after the end of the entity is blanked, so the line numbers stay the
ones of the original file.
"""

import re
from pathlib import Path

STANDARD_LIBRARIES = frozenset({"ieee", "std", "work"})
_LIBRARY = re.compile(r"^\s*library\s+(\w+)\s*;", re.IGNORECASE | re.MULTILINE)
_ENTITY_END = re.compile(
    r"^\s*end(\s+entity)?(\s+\w+)?\s*;", re.IGNORECASE | re.MULTILINE
)
_ENTITY_START = re.compile(r"^\s*entity\s+\w+\s+is\b", re.IGNORECASE | re.M)


def needs_vendor_library(text: str) -> bool:
    """Tell whether the text names a library of a vendor."""
    names = {match.group(1).lower() for match in _LIBRARY.finditer(text)}
    return bool(names - STANDARD_LIBRARIES)


def _comment_vendor(line: str) -> str:
    """Comment out a line that names a vendor library."""
    match = re.match(r"^\s*(library|use)\s+(\w+)", line, re.IGNORECASE)
    if match and match.group(2).lower() not in STANDARD_LIBRARIES:
        return "-- " + line
    return line


def entity_only(text: str) -> str:
    """Keep the context clauses and the entity declaration of a file.

    Parameters
    ----------
    text : str
        The VHDL source.

    Returns
    -------
    str
        The source with the vendor library lines commented out and the
        text after the entity blanked, with the same number of lines.
    """
    start = _ENTITY_START.search(text)
    end = _ENTITY_END.search(text, start.end()) if start else None
    keep = text if end is None else text[: end.end()]
    rest = "" if end is None else text[end.end() :]
    lines = [_comment_vendor(line) for line in keep.split("\n")]
    return "\n".join(lines) + re.sub(r"[^\n]", "", rest)


def write_stub(source: Path, target: Path) -> None:
    """Write the entity-only version of a file.

    Parameters
    ----------
    source : Path
        The original file.
    target : Path
        Where the reduced file goes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(entity_only(source.read_text()))
