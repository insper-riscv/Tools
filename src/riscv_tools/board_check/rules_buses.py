"""The rules about the external peripherals: V23 and V24."""

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import Finding, error, warning
from riscv_tools.board_inputs import board_view
from riscv_tools.board_ports import Placement, placements
from riscv_tools.board_schema import expand_group


def placed(ctx: Context) -> list[Placement]:
    """Put the external peripherals of the platform on the board.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Placement
        One for each external peripheral, in the order of the file.
    """
    return placements(ctx.platform, board_view(ctx.board))


def used_signals(ctx: Context) -> tuple[list[str], list[str]]:
    """List the signals of the board the external peripherals use.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    tuple of (list of str, list of str)
        The signals of the pins file and the prefixes (`VGA_`, for the
        video), for the rule of the inferred pins.
    """
    names: list[str] = []
    prefixes: list[str] = []
    for place in placed(ctx):
        if place.pins is None:
            continue
        if place.kind.role == "video":
            prefixes.append(f"{place.pins['video']}_")
            continue
        names += [
            n for spec in place.pins.values() for n in expand_group(spec)
        ]
    return names, prefixes


def _missing(place: Placement, board: str) -> Finding:
    """Word the finding of a peripheral the board cannot serve.

    Parameters
    ----------
    place : Placement
        The peripheral, with the reason.
    board : str
        The board name.

    Returns
    -------
    Finding
        The error (V23) of a required peripheral, else the warning that
        the peripheral is omitted.
    """
    where = (
        f"peripheral {place.name} (kind {place.kind.name}) on board '{board}'"
    )
    if place.need == "required":
        return error("V23", f"{where}: {place.reason}")
    return warning(
        "V23", f"{where}: {place.reason}; the peripheral is omitted"
    )


def _pin_findings(place: Placement) -> list[Finding]:
    """Check the pins a peripheral needs beyond the role (V24)."""
    wired = place.pins or {}
    if (
        place.kind.name == "adxl345"
        and place.item.get("three_wire") is False
        and "miso" not in wired
    ):
        return [
            error(
                "V24",
                f"peripheral {place.name}: three_wire false needs the "
                "pin miso, which the board role does not wire",
            )
        ]
    return []


def rule_buses(ctx: Context) -> list[Finding]:
    """Check the external peripherals against the board.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        V23 when the board lacks the role (or the copy, or the chip)
        that a peripheral uses, an error for a required peripheral and a
        warning for an optional one; V24 for a pin the entity needs
        and the board does not wire. Empty without external peripherals.
    """
    found: list[Finding] = []
    for place in placed(ctx):
        if place.pins is None:
            found.append(_missing(place, ctx.board.board))
        else:
            found += _pin_findings(place)
    return found
