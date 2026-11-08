"""Match every cable of the host to the boards it can be.

The algorithm of the identification plan, steps 1 to 5: the cables come
from `jtagconfig`, each gets the stable path of its USB port, each chain
is compared with the `jtag.chain` of the known boards, and the inventory
of the host ties a port to a board. The listing order never decides
between candidates.
"""

from collections.abc import Callable
from dataclasses import dataclass

from riscv_tools.board.inventory import Inventory, InventoryEntry
from riscv_tools.board_check import check_chain
from riscv_tools.board_schema import Board
from riscv_tools.board_schema.model import JtagDevice
from riscv_tools.jtag.hardware import Cable

PortResolver = Callable[[str], str | None]


@dataclass(frozen=True)
class CableReport:
    """What the host knows about one cable.

    Attributes
    ----------
    cable : Cable
        The cable and its chain.
    port : str or None
        The stable path of its USB port, None when the name has none.
    candidates : tuple of str
        The known boards whose chain this cable presents.
    entry : InventoryEntry or None
        The inventory entry of the port.
    problem : str or None
        Why the cable cannot be used, with the case number of the plan.
    """

    cable: Cable
    port: str | None
    candidates: tuple[str, ...]
    entry: InventoryEntry | None = None
    problem: str | None = None

    @property
    def boards(self) -> tuple[str, ...]:
        """Return the boards this cable may be.

        Returns
        -------
        tuple of str
            The board of the inventory entry when the port has one,
            else the candidates.
        """
        return (self.entry.board,) if self.entry else self.candidates


def cable_kind(cable: Cable) -> str:
    """Tell the kind of cable from the name `jtagconfig` gives it.

    Parameters
    ----------
    cable : Cable
        The cable.

    Returns
    -------
    str
        `usb-blaster-ii` for the `DE-SoC [USB-1]` and `USB-BlasterII`
        names, `usb-blaster` for the rest.
    """
    name = cable.name.lower()
    if name.startswith(("de-soc", "usb-blasterii", "usb-blaster ii")):
        return "usb-blaster-ii"
    return "usb-blaster"


def fpga_of(board: Board) -> JtagDevice:
    """Give the FPGA device of the chain of a board.

    Parameters
    ----------
    board : Board
        The board.

    Returns
    -------
    JtagDevice
        The element marked `fpga`, or the last one.
    """
    marked = [d for d in board.jtag.chain if d.fpga]
    return marked[0] if marked else board.jtag.chain[-1]


def chain_matches(board: Board, cable: Cable) -> bool:
    """Tell whether a cable presents the chain a board declares.

    The kind of cable must agree, and the chain is compared by the
    rule V17 of the validator (`board_check.check_chain`), so the
    comparison is written once.

    Parameters
    ----------
    board : Board
        The board.
    cable : Cable
        The cable.

    Returns
    -------
    bool
        True when the cable can be that board.
    """
    kind = board.jtag.cable
    if kind == "usb-blaster-ii" and cable_kind(cable) != kind:
        return False
    plain = kind in {"usb-blaster", "samd21-usbblaster"}
    if plain and cable_kind(cable) != "usb-blaster":
        return False
    observed = [d.idcode for d in cable.devices]
    return not check_chain(board, cable.name, observed)


def _problem(
    cable: Cable,
    candidates: tuple[str, ...],
    entry: InventoryEntry | None,
) -> str | None:
    """Say why a cable is unusable, or None."""
    if cable.broken:
        return (
            f"case 8: the chain of {cable.name} is broken "
            f"({cable.error}); only powering the board off and on fixes it"
        )
    if entry is not None and entry.board not in candidates:
        seen = ", ".join(d.idcode for d in cable.devices) or "none"
        return (
            f"IDCODE mismatch: {entry.id} ({entry.board}) is registered at "
            f"{entry.usb_path} but the cable answered {seen}"
        )
    if not candidates:
        seen = ", ".join(d.idcode for d in cable.devices) or "none"
        return (
            f"case 7: IDCODE {seen} on {cable.name} belongs to no known board"
        )
    return None


def scan(
    cables: list[Cable],
    boards: dict[str, Board],
    inventory: Inventory,
    resolve_port: PortResolver,
) -> list[CableReport]:
    """Identify every cable of the host.

    Parameters
    ----------
    cables : list of Cable
        The cables `jtagconfig` listed.
    boards : dict of {str: Board}
        The known boards.
    inventory : Inventory
        The inventory of the host.
    resolve_port : callable
        Maps the `<bus>-<port>` of a cable to its stable port path.

    Returns
    -------
    list of CableReport
        One per cable, ordered by port path (cables without one last),
        so the order does not depend on the listing of `jtagconfig`.
    """
    reports: list[CableReport] = []
    for cable in cables:
        bus = cable.bus_port
        port = resolve_port(bus) if bus else None
        candidates = tuple(
            name for name, item in boards.items() if chain_matches(item, cable)
        )
        entry = inventory.by_port(port)
        reports.append(
            CableReport(
                cable,
                port,
                candidates,
                entry,
                _problem(cable, candidates, entry),
            )
        )
    return sorted(
        reports, key=lambda r: (r.port is None, r.port or "", r.cable.name)
    )
