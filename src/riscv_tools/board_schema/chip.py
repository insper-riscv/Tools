"""Read a memory chip file (`Memory/chips/<chip>.yaml`)."""

from typing import Any

from riscv_tools.board_schema.fields import Section, present, raise_if
from riscv_tools.board_schema.model import Chip

CHIP_KINDS = ("sdram", "sram", "nor", "serial_flash")
SOURCES = ("datasheet", "inferido")
SDRAM_FIELDS = ("banks", "row_bits", "col_bits")


def _numbers(parent: Section, key: str, required: bool) -> dict[str, float]:
    """Read a mapping whose values are all numbers.

    Parameters
    ----------
    parent : Section
        The chip.
    key : str
        The field.
    required : bool
        Whether a missing field is a problem.

    Returns
    -------
    dict of str to float
        The values; empty when the field is absent.
    """
    section = parent.section(key, required=required)
    if section is None:
        return {}
    found: dict[str, float] = {}
    for name in section.names():
        value = section.number(name, minimum=0)
        if value is not None:
            found[name] = value
    section.done()
    return found


def _organization(parent: Section, kind: str | None) -> dict[str, int]:
    """Read the `organization` section.

    Parameters
    ----------
    parent : Section
        The chip.
    kind : str or None
        The kind of the chip, which decides the fields it needs.

    Returns
    -------
    dict of str to int
        The fields of the organization.
    """
    section = parent.section("organization")
    if section is None:
        return {}
    wanted = ["words", "width"]
    if kind == "sdram":
        wanted += list(SDRAM_FIELDS)
    elif kind is None:
        # Sem tipo válido o erro é o do tipo, não o dos campos.
        for name in SDRAM_FIELDS:
            section.get(name)
    found: dict[str, int] = {}
    for name in wanted:
        value = section.integer(name, minimum=1)
        if value is not None:
            found[name] = value
    section.done()
    return found


def parse_chip(raw: Any, label: str = "chip") -> Chip:
    """Read a chip file already merged over its `extends` chain.

    Parameters
    ----------
    raw : Any
        The parsed YAML.
    label : str, optional
        The name used in the messages.

    Returns
    -------
    Chip
        The chip.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section(label, raw, problems)
    name = top.text("chip")
    kind = top.text("kind", choices=CHIP_KINDS)
    organization = _organization(top, kind)
    cas = top.integer("cas_latency", required=False, minimum=1)
    timing = _numbers(top, "timing", True)
    io_timing = _numbers(top, "io_timing", False)
    max_mhz = top.number("max_mhz", required=False, minimum=0)
    sector = top.integer("sector_bytes", required=False, minimum=1)
    boot = top.integer("boot_sector_bytes", required=False, minimum=1)
    source = top.text("source", choices=SOURCES)
    top.done()
    raise_if(problems)
    return Chip(
        present(name),
        present(kind),
        organization["words"],
        organization["width"],
        organization,
        timing,
        io_timing,
        max_mhz,
        cas,
        sector,
        boot,
        present(source),
    )
