"""Boards the USB shows but whose JTAG chain is not readable yet."""

from dataclasses import dataclass

from riscv_tools.board.scan import CableReport
from riscv_tools.board.usb import USB_BLASTER, UsbDevice
from riscv_tools.board_schema.model import Board


@dataclass(frozen=True)
class UsbOnly:
    """A board seen on the USB without a chain.

    Attributes
    ----------
    board : str
        The board whose package lists the USB identifier.
    usb_id : str
        The `vid:pid` found by `lsusb`.
    state : str
        What the package says that identifier means.
    """

    board: str
    usb_id: str
    state: str


def usb_only(
    boards: dict[str, Board],
    usb: list[UsbDevice],
    reports: list[CableReport],
) -> list[UsbOnly]:
    """List the boards the USB shows but no cable chain explains.

    The USB identifiers come from `jtag.usb` of each package, so a new
    board with a cable of its own needs no code. The identifier of the
    plain USB-Blaster names no board and is skipped. A board that some
    cable already presents is not listed, and neither is a board that
    shares an identifier with one of those (the two DE-SoC boards).

    Parameters
    ----------
    boards : dict of str to Board
        The known boards.
    usb : list of UsbDevice
        The devices `lsusb` listed.
    reports : list of CableReport
        The cables `jtagconfig` listed, with the boards they may be.

    Returns
    -------
    list of UsbOnly
        One per board and identifier, in the order of the boards.
    """
    seen = {d.ident for d in usb}
    explained = {name for report in reports for name in report.candidates}
    taken = {
        item.usb_id.lower()
        for name in explained
        for item in boards[name].jtag.usb
    }
    return [
        UsbOnly(name, item.usb_id.lower(), item.state)
        for name, board in sorted(boards.items())
        if name not in explained
        for item in board.jtag.usb
        if item.usb_id.lower() in seen
        and item.usb_id.lower() not in taken | {USB_BLASTER}
    ]
