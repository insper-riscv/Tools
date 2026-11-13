"""The choices that define a new project and the checks on them."""

import re
from collections.abc import Collection
from dataclasses import dataclass

from riscv_tools.new_project.naming import check_slug, check_title

SECTOR_BYTES = 4096
BANK_COUNT = 2
_SIZE = re.compile(r"(\d+)([KM]?)")
_UNITS = {"": 1, "K": 1024, "M": 1024 * 1024}
_OFF_WORDS = ("off", "0", "no")


@dataclass(frozen=True)
class ProjectSpec:
    """What the person chose for the new project.

    A field left at None keeps the value of the template platform.

    Parameters
    ----------
    name : str
        Identifier of the project (the slug of its name): lower case
        letters, digits and hyphens. It names the platform, the folder
        and the files.
    board : str
        A board of the catalog.
    profile : str or None
        Profile of the core (`rv32im_zicclsm_zicntr_zihpm`).
    rom_bytes : int or None
        Size of the ROM (the FLASH region), in bytes.
    ram_bytes : int or None
        Size of the RAM region, in bytes.
    icache_bits : int or None
        Size of the instruction cache in bits; 0 turns it off.
    dcache_bits : int or None
        Size of the data cache in bits; 0 turns it off.
    title : str or None
        The name of the project as the person typed it; None means the
        identifier.
    """

    name: str
    board: str
    profile: str | None = None
    rom_bytes: int | None = None
    ram_bytes: int | None = None
    icache_bits: int | None = None
    dcache_bits: int | None = None
    title: str | None = None

    @property
    def display(self) -> str:
        """The name to show: as typed, or the identifier."""
        return self.name if self.title is None else self.title


def parse_size(text: str) -> int:
    """Read a size such as `64K`, `1M` or `4096` into bytes.

    Parameters
    ----------
    text : str
        The size, with an optional `K` or `M` suffix.

    Returns
    -------
    int
        The size in bytes.

    Raises
    ------
    ValueError
        If the text is not a positive size.
    """
    found = _SIZE.fullmatch(text.strip().upper())
    if found is None or int(found[1]) == 0:
        raise ValueError(f"size {text!r} must look like 64K, 1M or 4096")
    return int(found[1]) * _UNITS[found[2]]


def parse_cache(text: str) -> int:
    """Read the size of a cache in bits, or `off`.

    Parameters
    ----------
    text : str
        `off` (or `0`) or a number of bits.

    Returns
    -------
    int
        The size in bits; 0 for a cache that is off.

    Raises
    ------
    ValueError
        If the text is neither `off` nor a number of bits.
    """
    word = text.strip().lower()
    if word in _OFF_WORDS:
        return 0
    if not word.isdigit():
        raise ValueError(f"cache {text!r} must be off or a size in bits")
    return int(word)


def validate(
    spec: ProjectSpec,
    boards: Collection[str],
    profiles: Collection[str],
) -> None:
    """Check the choices against the catalog and the profile matrix.

    Parameters
    ----------
    spec : ProjectSpec
        The choices.
    boards : Collection of str
        The boards of the catalog.
    profiles : Collection of str
        The names of the valid profiles.

    Raises
    ------
    ValueError
        With the first problem found, naming what is accepted.
    """
    check_slug(spec.name)
    if spec.title is not None:
        check_title(spec.title)
    if spec.board not in boards:
        raise ValueError(
            f"unknown board {spec.board!r}; known: {', '.join(sorted(boards))}"
        )
    if spec.profile is not None and spec.profile not in profiles:
        raise ValueError(
            f"unknown profile {spec.profile!r}; list them with "
            "`riscv-tools profiles --spec Core/profiles/matrix.yaml "
            "--format names`"
        )
    unit = SECTOR_BYTES * BANK_COUNT
    if spec.rom_bytes is not None and spec.rom_bytes % unit:
        raise ValueError(
            f"the ROM holds two banks of whole {SECTOR_BYTES}-byte "
            f"sectors, so its size must be a multiple of {unit} bytes"
        )
    if spec.ram_bytes is not None and spec.ram_bytes % SECTOR_BYTES:
        raise ValueError(
            f"the RAM size must be a multiple of {SECTOR_BYTES} bytes"
        )
