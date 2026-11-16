"""The rules about the external peripherals: V23, V24 and V25."""

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import Finding, error, warning
from riscv_tools.board_inputs import board_view
from riscv_tools.board_ports import Placement, placements
from riscv_tools.board_schema import expand_group

# Os pares de dados do TMDS: azul, verde e vermelho.
TMDS_DATA_PAIRS = 3


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
    found: list[Finding] = []
    variant = place.variant
    needed = [
        pin.name
        for pin in (variant.pins if variant else ())
        if pin.required and pin.name not in wired
    ]
    if variant and needed:
        found.append(
            error(
                "V24",
                f"peripheral {place.name}: {variant.entity} needs the "
                f"pins {needed}, which the board role does not wire",
            )
        )
    if (
        place.kind.name == "adxl345"
        and place.item.get("three_wire") is False
        and "miso" not in wired
    ):
        found.append(
            error(
                "V24",
                f"peripheral {place.name}: three_wire false needs the "
                "pin miso, which the board role does not wire",
            )
        )
    found += _lane_findings(place, wired)
    found += _tmds_findings(place, wired)
    return found


def _tmds_findings(place: Placement, wired: dict[str, str]) -> list[Finding]:
    """Check that the pin `tmds` has the three data pairs (V24)."""
    if place.kind.name != "hdmi_tmds" or "tmds" not in wired:
        return []
    width = len(expand_group(wired["tmds"]))
    if width == TMDS_DATA_PAIRS:
        return []
    return [
        error(
            "V24",
            f"peripheral {place.name}: the board pin tmds has {width} "
            f"pairs, and hdmi_tmds_tx has {TMDS_DATA_PAIRS} data pairs",
        )
    ]


def _lane_findings(place: Placement, wired: dict[str, str]) -> list[Finding]:
    """Check that `lanes` of the camera is the width of the pin `d`."""
    if place.kind.name != "mipi" or "d" not in wired:
        return []
    width = len(expand_group(wired["d"]))
    lanes = int(place.item.get("lanes", width))
    if lanes == width:
        return []
    return [
        error(
            "V24",
            f"peripheral {place.name}: lanes {lanes} differs from the "
            f"{width} lanes of the board pin d",
        )
    ]


def _signals_of(place: Placement) -> set[str]:
    """List the signals of the board a placed peripheral wires."""
    return {
        signal
        for spec in (place.pins or {}).values()
        for signal in expand_group(spec)
    }


def _shared_signals(places: list[Placement]) -> list[Finding]:
    """Find a signal of the board that two peripherals wire (V25).

    Two entities that drive one pin (the I2C pair of the EEPROM and of
    the ADXL345 on the DE0-Nano) would make two ports of one name in
    the top and two drivers on the line, so the platform keeps only one.
    """
    owners: dict[str, list[str]] = {}
    for place in places:
        for signal in _signals_of(place):
            owners.setdefault(signal, []).append(place.name)
    return [
        error(
            "V25",
            f"signal {signal} is wired by the peripherals "
            f"{names}; one board pin takes only one of them",
        )
        for signal, names in owners.items()
        if len(names) > 1
    ]


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
        and the board does not wire; V25 for a signal that two
        peripherals wire. Empty without external peripherals.
    """
    found: list[Finding] = []
    places = placed(ctx)
    for place in places:
        if place.pins is None:
            found.append(_missing(place, ctx.board.board))
        else:
            found += _pin_findings(place)
    return found + _shared_signals(places)
