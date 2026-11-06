"""Record the cables of a host in its inventory (`scan --save`)."""

from dataclasses import replace

from riscv_tools.board.inventory import Inventory, InventoryEntry
from riscv_tools.board.scan import CableReport


def _new_id(board: str, host: str, taken: set[str]) -> str:
    """Pick the id of a new entry: `<board>-<host>`, numbered."""
    base = f"{board}-{host}"
    if base not in taken:
        return base
    number = 2
    while f"{base}-{number}" in taken:
        number += 1
    return f"{base}-{number}"


def _board_for(
    report: CableReport, port: str, assign: dict[str, str]
) -> str | None:
    """Give the certain board of a cable, or None."""
    chosen = assign.get(port)
    if chosen is not None:
        return chosen if chosen in report.candidates else None
    return report.candidates[0] if len(report.candidates) == 1 else None


def register(
    inventory: Inventory,
    reports: list[CableReport],
    assign: dict[str, str],
) -> tuple[Inventory, list[str]]:
    """Add to the inventory the cables it does not cover.

    A cable is registered when its port is known, no entry has the
    port, and the board is certain: the only candidate, or the one the
    user assigned to the port. A cable with several candidates and no
    assignment is left out and reported.

    Parameters
    ----------
    inventory : Inventory
        The current inventory.
    reports : list of CableReport
        The scan of the host.
    assign : dict of {str: str}
        Board by port path, the user's answer for ambiguous cables.

    Returns
    -------
    tuple of (Inventory, list of str)
        The new inventory and one note per cable that was left out.
    """
    entries = list(inventory.entries)
    taken = {e.id for e in entries}
    notes: list[str] = []
    for report in reports:
        if report.entry is not None or report.problem is not None:
            continue
        if report.port is None:
            notes.append(f"{report.cable.name}: no USB port path, not saved")
            continue
        board = _board_for(report, report.port, assign)
        if board is None:
            options = ", ".join(report.candidates)
            notes.append(
                f"{report.cable.name} at {report.port} may be {options}: "
                f"say which with --assign {report.port}=BOARD"
            )
            continue
        ident = _new_id(board, inventory.host, taken)
        taken.add(ident)
        entries.append(InventoryEntry(ident, board, report.port))
    return replace(inventory, entries=tuple(entries)), notes
