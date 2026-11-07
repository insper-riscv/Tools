"""Identify, select and lock the board that is plugged into a host."""

from riscv_tools.board.errors import BoardBusyError, BoardError
from riscv_tools.board.inventory import Inventory, InventoryEntry
from riscv_tools.board.lock import BoardLock
from riscv_tools.board.scan import CableReport, scan
from riscv_tools.board.select import (
    Environment,
    Request,
    Selection,
    present,
    select_board,
)

__all__ = [
    "BoardBusyError",
    "BoardError",
    "BoardLock",
    "CableReport",
    "Environment",
    "Inventory",
    "InventoryEntry",
    "Request",
    "Selection",
    "present",
    "scan",
    "select_board",
]
