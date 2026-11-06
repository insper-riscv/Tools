"""Helpers of the board identification tests: the host from fixtures."""

from pathlib import Path

from riscv_tools.board.inventory import Inventory, InventoryEntry
from riscv_tools.board.select import Environment
from riscv_tools.board.spec import load_boards
from riscv_tools.jtag.hardware import parse_jtagconfig

FIXTURES = Path(__file__).parent / "fixtures"
PORTS = {
    "1-2": "pci-0000:00:14.0-usb-0:2",
    "1-3": "pci-0000:00:14.0-usb-0:3",
    "1-4": "pci-0000:00:14.0-usb-0:4",
    "1-5": "pci-0000:00:14.0-usb-0:5",
    "1-6": "pci-0000:00:14.0-usb-0:6",
    "1-9": "pci-0000:00:14.0-usb-0:9",
}


def host(
    jtagconfig: str,
    entries: tuple[InventoryEntry, ...] = (),
    *,
    extra_boards: bool = False,
    busy: frozenset[str] = frozenset(),
) -> Environment:
    """Build the environment of a host from a `jtagconfig` fixture.

    Parameters
    ----------
    jtagconfig : str
        The name of the file in fixtures/jtagconfig, without `.txt`.
    entries : tuple of InventoryEntry
        The inventory of the host.
    extra_boards : bool
        Also know a second board with the IDCODE of the DE0-Nano.
    busy : frozenset of str
        The names of the lock files that are held.

    Returns
    -------
    Environment
        The host, with fake ports and locks.
    """
    directories = [FIXTURES / "boards"]
    if extra_boards:
        directories.append(FIXTURES / "boards-extra")
    text = (FIXTURES / "jtagconfig" / f"{jtagconfig}.txt").read_text()
    return Environment(
        load_boards(directories),
        Inventory("ws", Path("/locks"), entries),
        parse_jtagconfig(text),
        PORTS.get,
        lambda path: path.name not in busy,
    )
