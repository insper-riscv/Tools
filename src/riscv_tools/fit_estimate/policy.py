"""Policy of the fit check: thresholds, capacities and the V11 to V14.

The thresholds are constants of the Tools with no option to change them
or to force a result (decision DM7 of the Multi-FPGA plan): a resource
above its capacity is an error, one between 85 % and 100 % is a warning.
The same policy reads an estimate and a report of the Quartus.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.quartus_reports import Quantity, ResourceUsage

# Limiares em frações exatas (num/den), sem ponto flutuante.
WARN_NUM, WARN_DEN = 85, 100
ERROR_NUM, ERROR_DEN = 100, 100
MAX_LOGIC_ERROR_PCT = 10.0
RESOURCE_LABELS = (
    "logic",
    "RAM bits",
    "RAM blocks",
    "multipliers",
    "PLLs",
    "pins",
)
UNIT_NAMES = {"alm": "ALM", "le": "LE"}


class Level(Enum):
    """Result of the policy for one resource."""

    PASS = 0
    WARN = 1
    ERROR = 2


@dataclass(frozen=True)
class Finding:
    """One message of the fit check.

    Parameters
    ----------
    code : str
        Rule of the plan (``V11`` to ``V14`` and ``V18``).
    severity : str
        ``"E"`` or ``"W"``.
    message : str
        Text with the severity prefix, as section 8 of the plan has it.
    """

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class Capacity:
    """Capacities of the device, from ``resources`` of the board.

    Parameters
    ----------
    logic_unit : str
        ``"alm"`` or ``"le"``.
    logic : int
        Logic units of the device.
    ram_blocks : int
        Blocks of RAM.
    bits_per_block : int
        Bits of one block of RAM.
    multipliers : int
        Multipliers in the unit the Quartus counts.
    plls : int
        PLLs.
    user_pins : int or None
        User pins of the package, None when the board does not say.
    """

    logic_unit: str
    logic: int
    ram_blocks: int
    bits_per_block: int
    multipliers: int
    plls: int
    user_pins: int | None

    @property
    def ram_bits(self) -> int:
        """Bits of block memory of the device."""
        return self.ram_blocks * self.bits_per_block


def capacity_from_resources(resources: Mapping[str, Any]) -> Capacity:
    """Build the capacities from the ``resources`` map of a board.

    Parameters
    ----------
    resources : mapping
        The ``resources`` section of a ``board.yaml``.

    Returns
    -------
    Capacity
        The capacities.

    Raises
    ------
    ValueError
        When a resource is missing or has no number.
    """
    try:
        logic = resources["logic"]
        ram = resources["block_ram"]
        return Capacity(
            logic_unit=str(logic["unit"]),
            logic=int(logic["total"]),
            ram_blocks=int(ram["blocks"]),
            bits_per_block=int(ram["bits_per_block"]),
            multipliers=int(resources["multipliers"]["total"]),
            plls=int(resources["plls"]),
            user_pins=(
                None
                if resources.get("user_pins") is None
                else int(resources["user_pins"])
            ),
        )
    except (KeyError, TypeError) as error:
        msg = f"incomplete resources: {error!r}"
        raise ValueError(msg) from error


def load_capacity(path: Path) -> Capacity:
    """Read the capacities from a ``board.yaml``.

    Parameters
    ----------
    path : Path
        The ``board.yaml``.

    Returns
    -------
    Capacity
        The capacities of its ``resources`` section.

    Raises
    ------
    ValueError
        When the file has no ``resources`` section or it is incomplete.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        msg = f"{path}: not a mapping"
        raise ValueError(msg)
    resources = cast("Mapping[str, Any]", data).get("resources")
    if not isinstance(resources, Mapping):
        msg = f"{path}: no 'resources' section"
        raise ValueError(msg)
    return capacity_from_resources(cast("Mapping[str, Any]", resources))


def classify(used: int, total: int) -> Level:
    """Apply the policy: pass up to 85 %, warn up to 100 %, else error.

    Parameters
    ----------
    used : int
        Amount used or estimated.
    total : int
        Capacity.

    Returns
    -------
    Level
        PASS, WARN or ERROR.
    """
    if used * ERROR_DEN > total * ERROR_NUM:
        return Level.ERROR
    if used * WARN_DEN > total * WARN_NUM:
        return Level.WARN
    return Level.PASS


def _fmt(value: int) -> str:
    """Write an integer with the thousands separator."""
    return f"{value:,}"


def blocks_finding(
    blocks: int, capacity: Capacity, board: str
) -> Finding | None:
    """Check the estimated blocks of RAM (V11).

    Parameters
    ----------
    blocks : int
        Blocks the profile needs.
    capacity : Capacity
        Capacities of the board.
    board : str
        Name of the board, for the message.

    Returns
    -------
    Finding or None
        Error above the capacity, warning above 85 %, else None.
    """
    level = classify(blocks, capacity.ram_blocks)
    if level is Level.ERROR:
        util = blocks / capacity.ram_blocks
        return Finding(
            "V11",
            "E",
            f"E emulated memory needs {blocks} blocks above the "
            f"{capacity.ram_blocks} available on '{board}' "
            f"(utilization {util:.2f})",
        )
    if level is Level.WARN:
        pct = round(100 * blocks / capacity.ram_blocks)
        return Finding(
            "V11",
            "W",
            f"W emulated memory needs {blocks} blocks, {pct}% of the "
            f"{capacity.ram_blocks} available on '{board}'; "
            "only the fit decides",
        )
    return None


def logic_finding(
    estimate: int,
    capacity: Capacity,
    board: str,
    error_pct: float | None,
) -> Finding | None:
    """Check the estimated logic (V12 and V13).

    Parameters
    ----------
    estimate : int
        Estimated logic in the unit of the family.
    capacity : Capacity
        Capacities of the board.
    board : str
        Name of the board, for the message.
    error_pct : float or None
        Expected error of the family, for the message.

    Returns
    -------
    Finding or None
        V12 above the capacity, V13 between 85 % and 100 %, else None.
    """
    unit = UNIT_NAMES.get(capacity.logic_unit, capacity.logic_unit)
    level = classify(estimate, capacity.logic)
    if level is Level.ERROR:
        util = estimate / capacity.logic
        expected = (
            "" if error_pct is None else f", expected error {error_pct:.0f}%"
        )
        return Finding(
            "V12",
            "E",
            f"E estimated logic {_fmt(estimate)} {unit} exceeds "
            f"{_fmt(capacity.logic)} {unit} on '{board}' "
            f"(utilization {util:.2f}{expected})",
        )
    if level is Level.WARN:
        pct = round(100 * estimate / capacity.logic)
        return Finding(
            "V13",
            "W",
            f"W estimated logic {_fmt(estimate)} {unit} is {pct}% of "
            f"{_fmt(capacity.logic)} {unit} on '{board}'; "
            "only the fit decides",
        )
    return None


def uncalibrated_finding(family: str, reason: str | None = None) -> Finding:
    """Word V18: the family or a coefficient has no measurement.

    Parameters
    ----------
    family : str
        Identifier of the family.
    reason : str, optional
        What is missing, when it is a coefficient and not the table.

    Returns
    -------
    Finding
        The V18 warning.
    """
    if reason is None:
        text = (
            f"W family '{family}' has no calibration; capacity estimate "
            "skipped, only the fit decides"
        )
    else:
        text = (
            f"W family '{family}' has no measurement for {reason}; the "
            "logic estimate is a lower bound and does not fail the check, "
            "only the fit decides"
        )
    return Finding("V18", "W", text)


def _exceeds(
    label: str, quantity: Quantity | None, total: int | None
) -> str | None:
    """Return ``label used/total`` when the quantity is above total."""
    if quantity is None:
        return None
    limit = quantity.total if quantity.total is not None else total
    if limit is None or quantity.used <= limit:
        return None
    return f"{label} {_fmt(quantity.used)}/{_fmt(limit)}"


def _limits(cap: Capacity | None) -> tuple[int | None, ...]:
    """Return logic, RAM bits, blocks, multipliers, PLLs and pins."""
    if cap is None:
        return (None,) * len(RESOURCE_LABELS)
    return (
        cap.logic,
        cap.ram_bits,
        cap.ram_blocks,
        cap.multipliers,
        cap.plls,
        cap.user_pins,
    )


def _quantities(usage: ResourceUsage) -> tuple[Quantity | None, ...]:
    """Return the six resources in the order of RESOURCE_LABELS."""
    return (
        usage.logic,
        usage.ram_bits,
        usage.ram_blocks,
        usage.multipliers,
        usage.plls,
        usage.pins,
    )


def report_findings(
    usage: ResourceUsage, capacity: Capacity | None = None
) -> list[Finding]:
    """Compare a fitter report with the capacities (V14).

    Every resource over its limit is listed at once, not only the first.
    The limit is the capacity the report carries, or the one of
    ``capacity`` when the report has none (the synthesis).

    Parameters
    ----------
    usage : ResourceUsage
        Resources read from the fitter.
    capacity : Capacity, optional
        Capacities of the board, complementing those of the report.

    Returns
    -------
    list of Finding
        Empty, or one V14 error naming all resources over their limit.
        The slack band (85 % to 100 %) is a warning per resource.
    """
    unit = UNIT_NAMES.get(usage.logic_unit or "", "")
    labels = (f"logic {unit}".strip(), *RESOURCE_LABELS[1:])
    rows = list(
        zip(labels, _quantities(usage), _limits(capacity), strict=True)
    )
    names = [
        text
        for label, quantity, fallback in rows
        if (text := _exceeds(label, quantity, fallback))
    ]
    findings: list[Finding] = []
    if names:
        findings.append(
            Finding("V14", "E", "E fit report exceeds: " + "; ".join(names))
        )
    findings.extend(_tight(rows))
    return findings


def _tight(
    rows: Sequence[tuple[str, Quantity | None, int | None]],
) -> list[Finding]:
    """Warn for the resources between 85 % and 100 % of their limit."""
    out: list[Finding] = []
    for label, quantity, fallback in rows:
        if quantity is None:
            continue
        total = quantity.total if quantity.total is not None else fallback
        if total and classify(quantity.used, total) is Level.WARN:
            pct = round(100 * quantity.used / total)
            out.append(
                Finding(
                    "V14",
                    "W",
                    f"W fit report: {label} {_fmt(quantity.used)} is "
                    f"{pct}% of {_fmt(total)}; little slack",
                )
            )
    return out
