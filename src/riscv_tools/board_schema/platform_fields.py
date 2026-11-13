"""Read the board fields of a `platform.yaml`.

A platform that names a board (`board` or `boards`) also chooses the
backend of its external memories, its clocks, its console and the roles
of inputs and outputs it wants. The older fields (the map, the profile,
the peripherals) belong to the memory map module; this one reads only
the new ones, with the same checks of type as the other catalog files.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools.board_schema.board import role_section
from riscv_tools.board_schema.fields import Section, raise_if
from riscv_tools.board_schema.platform_video import (
    PlatformVideo,
    parse_platform_video,
)
from riscv_tools.config_files import read_config
from riscv_tools.memory_map.core_profile import normalize

BACKENDS = ("emulado", "dispositivo")
DEVICES = {
    "rom": ("nor", "flash-interna", "serial"),
    "ram": ("sdram", "sram"),
}
CONSOLES = ("jtag", "pinos")
NEEDS = ("required", "optional")
CLOCK_NAMES = ("core", "fetch", "mem")


@dataclass(frozen=True)
class MemoryUse:
    """How the platform realizes one external memory.

    Parameters
    ----------
    external : bool
        Whether the region sits behind the external port of the core.
    backend : str or None
        `emulado` or `dispositivo`, None for an internal region.
    device : str or None
        The kind of device, with the backend `dispositivo`.
    latency : tuple of int or None
        The first and the next access, in cycles, of an emulated memory.
    sector_bytes : int or None
        The sector of an emulated FLASH.
    """

    external: bool
    backend: str | None = None
    device: str | None = None
    latency: tuple[int, int] | None = None
    sector_bytes: int | None = None


@dataclass(frozen=True)
class Clock:
    """One clock the platform asks for.

    Parameters
    ----------
    mhz : float
        The frequency.
    phase_ps : int
        The phase against the reference, in picoseconds.
    """

    mhz: float
    phase_ps: int


@dataclass(frozen=True)
class IoNeed:
    """A role of inputs and outputs the platform wants.

    Parameters
    ----------
    count : int
        How many units (LEDs, switches, digits).
    need : str
        `required` or `optional`.
    """

    count: int
    need: str


@dataclass(frozen=True)
class PlatformBoardFields:
    """The board fields of a platform.

    Parameters
    ----------
    name : str
        The platform name.
    board : str
        `auto` or a board name.
    boards : tuple of str
        The boards the platform is built on.
    memories : dict of str to MemoryUse
        The external memories, keyed `rom` and `ram`.
    clocks : dict of str to Clock
        The clocks, keyed `core`, `fetch` and `mem`.
    console : str
        `jtag` or `pinos`.
    io : dict of str to IoNeed
        The roles of inputs and outputs.
    top : tuple of str
        The components whose closure holds the `needs`.
    video : PlatformVideo or None
        What the platform asks of the video output; None when it asks
        for none.
    """

    name: str
    board: str
    boards: tuple[str, ...]
    memories: dict[str, MemoryUse]
    clocks: dict[str, Clock]
    console: str
    io: dict[str, IoNeed]
    top: tuple[str, ...]
    video: PlatformVideo | None = None

    def candidates(self) -> tuple[str, ...]:
        """List the boards the platform has to be checked against.

        Returns
        -------
        tuple of str
            The named board and the `boards` list, without repeats;
            empty when the board is `auto` and the list is empty.
        """
        named = () if self.board == "auto" else (self.board,)
        return tuple(dict.fromkeys((*named, *self.boards)))


def declares_board(platform: dict[str, Any]) -> bool:
    """Tell whether a platform uses the board fields.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    bool
        True when `board` or `boards` is written.
    """
    return "board" in platform or "boards" in platform


def _is_power_of_two(value: int) -> bool:
    """Tell whether an integer is a power of two.

    Parameters
    ----------
    value : int
        The number.

    Returns
    -------
    bool
        True when exactly one bit is set.
    """
    return value > 0 and value & (value - 1) == 0


def _latency(entry: Section) -> tuple[int, int] | None:
    """Read the `latency` of an emulated memory.

    Parameters
    ----------
    entry : Section
        The memory.

    Returns
    -------
    tuple of int or None
        The first and the next access.
    """
    latency = entry.section("latency", required=False)
    if latency is None:
        return None
    first = latency.integer("first", minimum=1)
    following = latency.integer("next", minimum=1)
    latency.done()
    return None if first is None or following is None else (first, following)


def _check_combination(entry: Section, key: str, use: MemoryUse) -> None:
    """Check which fields may appear together in a memory.

    Parameters
    ----------
    entry : Section
        The memory.
    key : str
        `rom` or `ram`.
    use : MemoryUse
        What was read.
    """
    if use.external and use.backend is None:
        entry.fail("backend", "is required when external is true")
    if not use.external and "backend" in entry.raw:
        entry.fail("backend", "is only valid when external is true")
    if use.backend == "dispositivo" and "device" not in entry.raw:
        entry.fail("device", "is required with the backend dispositivo")
    if use.backend != "dispositivo" and "device" in entry.raw:
        entry.fail("device", "is only valid with the backend dispositivo")
    _check_emulated_only(entry, key, use)


def _check_emulated_only(entry: Section, key: str, use: MemoryUse) -> None:
    """Check the fields that only an emulated memory may have.

    Parameters
    ----------
    entry : Section
        The memory.
    key : str
        `rom` or `ram`.
    use : MemoryUse
        What was read.
    """
    if use.backend != "emulado" and "latency" in entry.raw:
        entry.fail("latency", "is only valid with the backend emulado")
    if key == "ram" and "sector_bytes" in entry.raw:
        entry.fail("sector_bytes", "is only valid for the FLASH (rom)")
    if "sector_bytes" in entry.raw and use.backend != "emulado":
        entry.fail("sector_bytes", "is only valid with the backend emulado")


def _memory_use(parent: Section, key: str) -> MemoryUse | None:
    """Read `memory.rom` or `memory.ram`.

    Parameters
    ----------
    parent : Section
        The `memory` section.
    key : str
        `rom` or `ram`.

    Returns
    -------
    MemoryUse or None
        The memory; None when it is absent.
    """
    entry = parent.section(key, required=False)
    if entry is None:
        return None
    external = entry.flag("external")
    backend = entry.text("backend", required=False, choices=BACKENDS)
    device = entry.text("device", required=False, choices=DEVICES[key])
    latency = _latency(entry)
    sector = entry.integer("sector_bytes", required=False, minimum=1)
    if sector is not None and not _is_power_of_two(sector):
        entry.fail("sector_bytes", "must be a power of 2")
    use = MemoryUse(external, backend, device, latency, sector)
    _check_combination(entry, key, use)
    return use


def _clocks(top: Section) -> dict[str, Clock]:
    """Read the `clocks` section.

    Parameters
    ----------
    top : Section
        The platform.

    Returns
    -------
    dict of str to Clock
        The clocks the platform asks for.
    """
    section = top.section("clocks")
    found: dict[str, Clock] = {}
    if section is None:
        return found
    for name in CLOCK_NAMES:
        entry = section.section(name, required=name == "core")
        if entry is None:
            continue
        mhz = entry.number("mhz", minimum=0)
        phase = entry.integer("phase_ps", required=False)
        entry.done()
        if mhz is not None:
            found[name] = Clock(mhz, phase or 0)
    section.done()
    return found


def _io(top: Section) -> dict[str, IoNeed]:
    """Read the `io` section.

    Parameters
    ----------
    top : Section
        The platform.

    Returns
    -------
    dict of str to IoNeed
        The roles the platform wants.
    """
    section = top.section("io", required=False)
    found: dict[str, IoNeed] = {}
    if section is None:
        return found
    for role in section.names():
        entry = role_section(section, role)
        if entry is None:
            continue
        count = entry.integer("count", minimum=1)
        need = entry.text("need", choices=NEEDS)
        entry.done()
        if count is not None and need is not None:
            found[role] = IoNeed(count, need)
    return found


def _memories(top: Section) -> dict[str, MemoryUse]:
    """Read the external memories of the `memory` section.

    Parameters
    ----------
    top : Section
        The platform.

    Returns
    -------
    dict of str to MemoryUse
        The memories, keyed `rom` and `ram`.
    """
    memory = top.section("memory")
    found: dict[str, MemoryUse] = {}
    if memory is None:
        return found
    for key in DEVICES:
        use = _memory_use(memory, key)
        if use is not None:
            found[key] = use
    return found


def parse_platform_fields(platform: dict[str, Any]) -> PlatformBoardFields:
    """Read the board fields of a platform, checking their types.

    The fields of the map are not read here, and the keys this function
    does not know are left to the module that owns them.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    PlatformBoardFields
        The fields.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section("platform", platform, problems)
    name = top.text("platform", required=False) or ""
    board = top.text("board", required=False) or "auto"
    boards = top.texts("boards", required=False)
    memories = _memories(top)
    clocks = _clocks(top)
    console = top.text("console", required=False, choices=CONSOLES) or "jtag"
    roles = _io(top)
    needed = top.one_or_more("top") if "top" in platform else ()
    video = parse_platform_video(
        platform, top.section("io", required=False), problems
    )
    if any(m.backend == "dispositivo" for m in memories.values()) and (
        "mem" not in clocks
    ):
        problems.append("platform.clocks.mem is required with a device")
    raise_if(problems)
    return PlatformBoardFields(
        name,
        board,
        tuple(boards),
        memories,
        clocks,
        console,
        roles,
        needed,
        video,
    )


def read_platform_file(path: Path) -> dict[str, Any]:
    """Read a platform file with its `extends:` chain resolved.

    Parameters
    ----------
    path : Path
        The platform YAML.

    Returns
    -------
    dict of str to Any
        The platform merged over its bases.
    """
    data = read_config(path)
    normalize(data, path)
    return data
