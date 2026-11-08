"""Read the resource summaries that the Quartus writes.

Three files carry the resources of a compilation: the summary of the
synthesis (``<revision>.map.summary``), the summary of the fitter
(``<revision>.fit.summary``) and the tables of the reports
(``<revision>.map.rpt``, ``<revision>.fit.rpt``). The summaries are
``Name : value`` lines; the reports are boxed tables. The synthesis
leaves ``N/A`` in the logic line of its summary, and the estimate of the
logic lives in the table of resource usage of ``map.rpt``.

The module reads the three kinds of file of every family of the project
(ALMs on the Cyclone V; logic elements on the Cyclone IV E, the MAX 10
and the Cyclone 10 LP). It only reads: the capacities, the limits and
the policy belong to ``fit_estimate``.
"""

import re
from dataclasses import dataclass, field

LOGIC_LABELS = {
    "Logic utilization (in ALMs)": "alm",
    "Estimate of Logic utilization (ALMs needed)": "alm",
    "Logic utilization (ALMs needed / total ALMs on device)": "alm",
    "Total logic elements": "le",
}
RAM_BIT_LABELS = ("Total block memory bits", "Total memory bits")
RAM_BLOCK_LABELS = ("Total RAM Blocks",)
MULTIPLIER_LABELS = (
    "Total DSP Blocks",
    "Embedded Multiplier 9-bit elements",
)
PLL_LABELS = ("Total PLLs",)
PIN_LABELS = ("Total pins", "I/O pins")
REGISTER_LABELS = ("Total registers", "Dedicated logic registers")
META_LABELS = {
    "Fitter Status": "status",
    "Analysis & Synthesis Status": "status",
    "Quartus Prime Version": "version",
    "Revision Name": "revision",
    "Top-level Entity Name": "top_entity",
    "Family": "family",
    "Device": "device",
}
_NUMBER = re.compile(r"^\s*([\d,]+)\s*(?:/\s*([\d,]+))?")
_SUMMARY_LINE = re.compile(r"^(?P<key>[^:]+?)\s*:\s*(?P<value>.*)$")
_TABLE_ROW = re.compile(r"^;\s*(?P<label>[^;]*?)\s*;\s*(?P<usage>[^;]*?)\s*;")
_ENTITY_ROW = re.compile(
    r"^;(?P<indent> *)\|(?P<name>[^;|]+?)\|?\s*;\s*(?P<alut>\d+)"
    r"(?: \(\d+\))?\s*;\s*(?P<regs>\d+)(?: \(\d+\))?\s*;\s*"
    r"(?P<bits>\d+)\s*;"
)
_STATUS_WORD = re.compile(r"^(\w+)")
UNIT_STEP = 3
TABLE_BORDERS = 3


@dataclass(frozen=True)
class Quantity:
    """A resource as the Quartus reports it.

    Parameters
    ----------
    used : int
        Amount used (or estimated).
    total : int or None
        Capacity of the device, ``None`` when the file does not carry it
        (the synthesis does not know the fitter's totals).
    """

    used: int
    total: int | None = None


@dataclass(frozen=True)
class Entity:
    """One row of the table of resource use by entity of ``map.rpt``.

    Parameters
    ----------
    name : str
        Name of the instance in the hierarchy.
    depth : int
        Depth in the hierarchy (0 for the top).
    luts : int
        Combinational ALUTs, with the ones of the children.
    registers : int
        Dedicated logic registers, with the ones of the children.
    memory_bits : int
        Block memory bits, with the ones of the children.
    """

    name: str
    depth: int
    luts: int
    registers: int
    memory_bits: int


@dataclass(frozen=True)
class ResourceUsage:
    """The resources of one compilation step, by kind.

    Parameters
    ----------
    logic_unit : str or None
        ``"alm"`` or ``"le"``, the unit of ``logic``.
    logic : Quantity or None
        ALMs or logic elements.
    ram_bits : Quantity or None
        Bits of block memory.
    ram_blocks : Quantity or None
        Blocks of RAM (M10K, M9K).
    multipliers : Quantity or None
        DSP blocks or embedded multiplier elements.
    plls : Quantity or None
        PLLs.
    pins : Quantity or None
        Pins.
    registers : int or None
        Dedicated logic registers.
    meta : dict of {str: str}
        ``status``, ``version``, ``revision``, ``top_entity``,
        ``family`` and ``device`` when the file has them.
    entities : tuple of Entity
        Hierarchy of ``map.rpt`` (empty for the other files).
    """

    logic_unit: str | None = None
    logic: Quantity | None = None
    ram_bits: Quantity | None = None
    ram_blocks: Quantity | None = None
    multipliers: Quantity | None = None
    plls: Quantity | None = None
    pins: Quantity | None = None
    registers: int | None = None
    meta: dict[str, str] = field(default_factory=dict[str, str])
    entities: tuple[Entity, ...] = ()


def parse_quantity(text: str) -> Quantity | None:
    """Read ``8,058 / 18,480 ( 44 % )`` or ``4638``; ``N/A`` is None.

    Parameters
    ----------
    text : str
        Value of a summary line or cell of a table.

    Returns
    -------
    Quantity or None
        The amount and the capacity when there is one; None when the
        text does not start with a number.
    """
    found = _NUMBER.match(text)
    if found is None:
        return None
    used = int(found.group(1).replace(",", ""))
    total = found.group(2)
    return Quantity(used, int(total.replace(",", "")) if total else None)


def _pairs_of_summary(text: str) -> list[tuple[str, str]]:
    """Return the ``(name, value)`` pairs of a summary file."""
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        found = _SUMMARY_LINE.match(line.strip())
        if found:
            pairs.append((found.group("key"), found.group("value")))
    return pairs


def _pairs_of_table(text: str, title: str) -> list[tuple[str, str]]:
    """Return the ``(label, usage)`` rows of the table ``title``."""
    rows: list[tuple[str, str]] = []
    inside = False
    borders = 0
    for line in text.splitlines():
        if not inside:
            inside = line.startswith(f"; {title}")
            continue
        if line.startswith("+"):
            borders += 1
            # Bordas: depois do título, do cabeçalho e do fim da tabela.
            if borders == TABLE_BORDERS:
                break
            continue
        row = _usage_row(line)
        if row is not None:
            rows.append(row)
    return rows


def _usage_row(line: str) -> tuple[str, str] | None:
    """Return the ``(label, usage)`` of a table line, or None."""
    found = _TABLE_ROW.match(line)
    if found is None:
        return None
    label, usage = found.group("label"), found.group("usage")
    if label in ("Resource", "") or usage == "Usage":
        return None
    return label, usage


def _field_of(label: str) -> str | None:
    """Return the ResourceUsage quantity a table label feeds, if any."""
    for name, labels in (
        ("ram_bits", RAM_BIT_LABELS),
        ("ram_blocks", RAM_BLOCK_LABELS),
        ("multipliers", MULTIPLIER_LABELS),
        ("plls", PLL_LABELS),
        ("pins", PIN_LABELS),
    ):
        if label in labels:
            return name
    return None


def _usage_of_pairs(
    pairs: list[tuple[str, str]],
    entities: tuple[Entity, ...] = (),
) -> ResourceUsage:
    """Fold ``(label, value)`` pairs into a ResourceUsage."""
    fields: dict[str, Quantity | None] = {}
    meta: dict[str, str] = {}
    unit: str | None = None
    registers: int | None = None
    for label, value in pairs:
        quantity = parse_quantity(value)
        if label in LOGIC_LABELS and quantity is not None:
            unit = LOGIC_LABELS[label]
            fields.setdefault("logic", quantity)
            continue
        name = _field_of(label)
        if name is not None and quantity:
            fields.setdefault(name, quantity)
        elif label in REGISTER_LABELS and quantity and registers is None:
            registers = quantity.used
        elif label in META_LABELS:
            meta.setdefault(META_LABELS[label], value.strip())
    return ResourceUsage(
        logic_unit=unit,
        logic=fields.get("logic"),
        ram_bits=fields.get("ram_bits"),
        ram_blocks=fields.get("ram_blocks"),
        multipliers=fields.get("multipliers"),
        plls=fields.get("plls"),
        pins=fields.get("pins"),
        registers=registers,
        meta=meta,
        entities=entities,
    )


def parse_summary(text: str) -> ResourceUsage:
    """Read a ``*.map.summary`` or ``*.fit.summary`` file.

    Parameters
    ----------
    text : str
        Contents of the summary.

    Returns
    -------
    ResourceUsage
        The resources of the file. In the synthesis summary the logic of
        the ALM families is ``N/A`` and so ``logic`` is None.

    Raises
    ------
    ValueError
        When the text has no resource line at all.
    """
    usage = _usage_of_pairs(_pairs_of_summary(text))
    if not usage.meta and usage.logic is None and usage.pins is None:
        msg = "no Quartus summary line found"
        raise ValueError(msg)
    return usage


def parse_entities(text: str, depth_limit: int = 2) -> tuple[Entity, ...]:
    """Read the hierarchy table of ``map.rpt`` down to a depth.

    Parameters
    ----------
    text : str
        Contents of ``map.rpt``.
    depth_limit : int, optional
        Deepest level kept (0 is the top), by default 2.

    Returns
    -------
    tuple of Entity
        The rows of "Analysis & Synthesis Resource Utilization by
        Entity" down to ``depth_limit``, in file order.
    """
    rows: list[Entity] = []
    for line in text.splitlines():
        found = _ENTITY_ROW.match(line)
        if found is None:
            continue
        depth = (len(found.group("indent")) - 1) // UNIT_STEP
        if depth <= depth_limit:
            rows.append(
                Entity(
                    name=found.group("name").strip(),
                    depth=depth,
                    luts=int(found.group("alut")),
                    registers=int(found.group("regs")),
                    memory_bits=int(found.group("bits")),
                )
            )
    return tuple(rows)


def parse_map_report(
    report: str, summary: str | None = None, depth_limit: int = 2
) -> ResourceUsage:
    """Read the synthesis: the logic estimate of ``map.rpt``.

    Parameters
    ----------
    report : str
        Contents of ``<revision>.map.rpt``.
    summary : str, optional
        Contents of ``<revision>.map.summary``; its status, version and
        pin lines complete the ones of the report.
    depth_limit : int, optional
        Depth of the hierarchy kept, by default 2.

    Returns
    -------
    ResourceUsage
        The resources after the synthesis, with the logic estimate.

    Raises
    ------
    ValueError
        When the report has no table of resource usage.
    """
    pairs = _pairs_of_table(report, "Analysis & Synthesis Resource Usage")
    if not pairs:
        msg = "no 'Analysis & Synthesis Resource Usage Summary' table"
        raise ValueError(msg)
    head = _pairs_of_table(report, "Analysis & Synthesis Summary")
    summary_pairs = _pairs_of_summary(summary) if summary else []
    # O resumo vem primeiro: os PLLs e os pinos dele são os do projeto,
    # os da tabela contam também contadores internos do PLL.
    return _usage_of_pairs(
        summary_pairs + pairs + head,
        parse_entities(report, depth_limit),
    )


def parse_fit_report(report: str, summary: str | None = None) -> ResourceUsage:
    """Read the fitter: capacities and use, from its summary or report.

    Parameters
    ----------
    report : str or None
        Contents of ``<revision>.fit.rpt``; used for what the summary
        does not carry.
    summary : str, optional
        Contents of ``<revision>.fit.summary``, the preferred source.

    Returns
    -------
    ResourceUsage
        The resources after the fit, each with its capacity.

    Raises
    ------
    ValueError
        When neither text has a resource line.
    """
    pairs = _pairs_of_summary(summary) if summary else []
    pairs += _pairs_of_table(report or "", "Fitter Resource Usage Summary")
    usage = _usage_of_pairs(pairs)
    if usage.logic is None and usage.pins is None:
        msg = "no fitter resource line found"
        raise ValueError(msg)
    return usage


def succeeded(usage: ResourceUsage) -> bool:
    """Tell whether the step ended with ``Successful``.

    Parameters
    ----------
    usage : ResourceUsage
        Resources read from a summary.

    Returns
    -------
    bool
        True when the status line starts with ``Successful``.
    """
    word = _STATUS_WORD.match(usage.meta.get("status", ""))
    return word is not None and word.group(1) == "Successful"
