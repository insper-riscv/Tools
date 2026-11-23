"""Which generics the toplevel of a simulation declares.

A platform can switch a generic off (`ROM_FILE: false`) when its
toplevel has no such generic, for example a top whose FLASH sits in the
SDRAM chip and so has no `rom_file`. GHDL refuses `-gROM_FILE=False` for
a generic the entity does not have, so the runner leaves out a parameter
that is off and that the toplevel does not declare. An enabled parameter
is always passed, and an undeclared one then fails in GHDL with its own
message.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_OFF = ("false", "off")
_NAMES = re.compile(r"^\s*(\w+(?:\s*,\s*\w+)*)\s*:", re.MULTILINE)


def _generic_clause(text: str, toplevel: str) -> str | None:
    """Return the text of the generic clause of an entity.

    Parameters
    ----------
    text : str
        The VHDL source, comments already removed.
    toplevel : str
        The entity to look for.

    Returns
    -------
    str or None
        The clause (up to its `port` or the end of the entity); None
        when the source does not hold the entity.
    """
    start = re.search(rf"\bentity\s+{re.escape(toplevel)}\s+is\b", text, re.I)
    if start is None:
        return None
    body = text[start.end() :]
    end = re.search(r"^\s*end\b", body, re.I | re.MULTILINE)
    body = body[: end.start()] if end else body
    port = re.search(r"^\s*port\s*\(", body, re.I | re.MULTILINE)
    return body[: port.start()] if port else body


def _vhdl_text(path: Path) -> str:
    """Read a VHDL file without comments; empty for anything else."""
    if path.suffix.lower() not in (".vhd", ".vhdl") or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"--[^\n]*", "", text)


def _names_of(clause: str) -> set[str]:
    """List the names a generic clause declares, in lowercase."""
    return {
        name.strip().lower()
        for group in _NAMES.findall(clause)
        for name in group.split(",")
    }


def declared_generics(
    sources: Iterable[str], toplevel: str
) -> set[str] | None:
    """List the generics of the toplevel entity, in lowercase.

    Parameters
    ----------
    sources : iterable of str
        The VHDL files of the simulation.
    toplevel : str
        The toplevel entity.

    Returns
    -------
    set of str or None
        The generic names; None when no file declares the entity, so
        nothing is assumed about it.
    """
    for source in sources:
        text = _vhdl_text(Path(source))
        clause = _generic_clause(text, toplevel) if text else None
        if clause is not None:
            return _names_of(clause)
    return None


def _is_off(value: Any) -> bool:
    """Tell whether a parameter value switches the generic off."""
    return value is False or str(value).strip().lower() in _OFF


def without_undeclared_off(
    parameters: Mapping[str, Any], declared: set[str] | None
) -> dict[str, Any]:
    """Drop the parameters that are off and the toplevel lacks.

    Parameters
    ----------
    parameters : mapping of {str: Any}
        The `sim.parameters`, with their templates filled.
    declared : set of str or None
        The generics of the toplevel (`declared_generics`); None keeps
        every parameter.

    Returns
    -------
    dict of {str: Any}
        The parameters to pass to GHDL.
    """
    if declared is None:
        return dict(parameters)
    return {
        name: value
        for name, value in parameters.items()
        if name.lower() in declared or not _is_off(value)
    }
