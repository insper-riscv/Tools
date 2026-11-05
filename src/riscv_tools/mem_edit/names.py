"""Find In-System Memory Content Editor instances by name.

The index of an instance changes whenever the design gains or loses a
memory with ENABLE_RUNTIME_MOD, while the INSTANCE_NAME of the IP stays.
The config names the memories (quartus.rom_mem_names and
quartus.ram_mem_name) and this module turns the names into the indices
of the board that is programmed now. The board is listed once per link
and the listing is kept until the board is programmed again.
"""

from dataclasses import dataclass
from typing import Any

from riscv_tools.jtag import JtagLink, run_tcl

# The editor keeps only the first characters of an INSTANCE_NAME: a
# name listed with exactly this many may be the start of a longer one.
NAME_LIMIT = 4

# Fields of a MEM line before the name (MEM, index, depth, width,
# mode and type).
_MEM_FIELDS = 6


class MemNameError(LookupError):
    """A configured memory name has no usable instance on the board."""


@dataclass(frozen=True)
class MemInstance:
    """One editable memory instance of the programmed board.

    Attributes
    ----------
    index : int
        The instance index the editor commands take.
    depth : int
        Number of words.
    width : int
        Width of a word, in bits.
    name : str
        The name as the editor lists it, empty for an unnamed instance.
    """

    index: int
    depth: int
    width: int
    name: str


_LISTINGS: dict[JtagLink, list[MemInstance]] = {}


def parse_listing(text: str) -> list[MemInstance]:
    """Read the output of list_mems.tcl.

    Parameters
    ----------
    text : str
        The standard output of the script: MEM lines and a COUNT line.
        Other lines are ignored.

    Returns
    -------
    list of MemInstance
        The instances, in the order listed.

    Raises
    ------
    RuntimeError
        The output has no COUNT line, or the COUNT does not match the
        MEM lines, so the listing is incomplete.
    """
    found: list[MemInstance] = []
    count: int | None = None
    for line in text.splitlines():
        fields = line.split(None, _MEM_FIELDS)
        if line.startswith("COUNT="):
            count = int(line.split("=", 1)[1])
        elif len(fields) >= _MEM_FIELDS and fields[0] == "MEM":
            name = (
                fields[_MEM_FIELDS].strip()
                if len(fields) > _MEM_FIELDS
                else ""
            )
            found.append(
                MemInstance(
                    int(fields[1]), int(fields[2]), int(fields[3]), name
                )
            )
    if count is None or count != len(found):
        raise RuntimeError(
            f"list_mems.tcl produced an incomplete listing:\n{text}"
        )
    return found


def instances(link: JtagLink) -> list[MemInstance]:
    """List the editable memory instances of the programmed board.

    The board is asked once per link; later calls return the same
    listing until invalidate() runs.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to list.

    Returns
    -------
    list of MemInstance
        The instances, in the order of their indices.
    """
    if link not in _LISTINGS:
        _LISTINGS[link] = parse_listing(run_tcl(link, "list_mems.tcl").stdout)
    return _LISTINGS[link]


def invalidate() -> None:
    """Forget every listing, because the board is programmed again."""
    _LISTINGS.clear()


def describe(found: list[MemInstance]) -> str:
    """Describe the instances for an error message.

    Parameters
    ----------
    found : list of MemInstance
        The instances of the board.

    Returns
    -------
    str
        One entry per instance with its name and index, or a note that
        the board has none.
    """
    if not found:
        return "the board has no editable memory instances"
    return "the board has " + ", ".join(
        f"{inst.name or '(no name)'} (index {inst.index}, "
        f"{inst.depth}x{inst.width})"
        for inst in found
    )


def _matches(listed: str, wanted: str) -> bool:
    """Tell whether the listed name is the wanted one."""
    if listed == wanted:
        return True
    return len(listed) >= NAME_LIMIT and wanted.startswith(listed)


def find(found: list[MemInstance], wanted: str) -> list[MemInstance]:
    """Pick the instances that carry a name.

    Parameters
    ----------
    found : list of MemInstance
        The instances of the board.
    wanted : str
        The INSTANCE_NAME of the IP.

    Returns
    -------
    list of MemInstance
        Every instance listed under that name; the editor cuts long
        names, so a name listed with the maximum length also matches a
        longer wanted name that starts with it.

    Raises
    ------
    MemNameError
        No instance carries the name; the message lists the instances.
    """
    chosen = [inst for inst in found if _matches(inst.name, wanted)]
    if not chosen:
        raise MemNameError(
            f"no memory instance named {wanted!r}: {describe(found)}"
        )
    return chosen


def _as_names(value: Any) -> list[str]:
    """Turn a configured name or list of names into a list of names."""
    if isinstance(value, str):
        return [value]
    return [str(name) for name in value]


def rom_instances(link: JtagLink, cfg: dict[str, Any]) -> list[int]:
    """Get the indices of the ROM instances to write.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to list, when names are configured.
    cfg : dict of {str: Any}
        The merged project config; quartus.rom_mem_names wins over
        quartus.rom_mem_instances when both are set.

    Returns
    -------
    list of int
        The indices, in the order of the names, without repeats. A name
        the editor listed cut short (for example FLASH and FLASH_MEM
        both as FLAS) stands for every instance with that start; they
        hold the same image, so all of them are written.

    Raises
    ------
    MemNameError
        A configured name is not on the board.
    """
    quartus = cfg["quartus"]
    names = quartus.get("rom_mem_names")
    if not names:
        return list(quartus["rom_mem_instances"])
    found = instances(link)
    indices: list[int] = []
    for name in _as_names(names):
        indices += [
            i.index for i in find(found, name) if i.index not in indices
        ]
    return indices


def ram_instance(link: JtagLink, cfg: dict[str, Any]) -> int:
    """Get the index of the RAM instance.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to list, when a name is configured.
    cfg : dict of {str: Any}
        The merged project config; quartus.ram_mem_name wins over
        quartus.ram_mem_instance when both are set.

    Returns
    -------
    int
        The index of the instance.

    Raises
    ------
    MemNameError
        The name is not on the board, or more than one instance carries
        it, so the RAM cannot be told apart.
    """
    quartus = cfg["quartus"]
    name = quartus.get("ram_mem_name")
    if not name:
        return int(quartus["ram_mem_instance"])
    found = instances(link)
    chosen = find(found, str(name))
    if len(chosen) > 1:
        raise MemNameError(
            f"the name {name!r} fits {len(chosen)} instances, "
            f"{describe(chosen)}; the editor keeps only the first "
            f"{NAME_LIMIT} characters of a name, so give the RAM a name "
            "that differs from the others in them"
        )
    return chosen[0].index
