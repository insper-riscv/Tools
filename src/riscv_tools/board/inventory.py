"""The inventory of the boards of a host.

```yaml
host: ws                       # optional, default: short hostname
lock_dir: /tmp                 # optional, default: /tmp
boards:
- {id: de0-cv-ws, board: de0-cv, usb_path: "pci-0000:00:14.0-usb-0:2"}
- {id: de2-115-ws, board: de2-115, usb_path: "pci-0000:00:14.0-usb-0:3"}
```

The file is `~/.config/riscv-tools/boards.yaml`, or
`/etc/riscv-tools/boards.yaml` for all users; the first that exists is
used. A host without the file still identifies a board that has a single
candidate, and takes the lock file from the board and the host.
"""

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.board.errors import BoardError

DEFAULT_LOCK_DIR = Path("/tmp")  # noqa: S108
USER_FILE = Path("~/.config/riscv-tools/boards.yaml")
SYSTEM_FILE = Path("/etc/riscv-tools/boards.yaml")


@dataclass(frozen=True)
class InventoryEntry:
    """One board of the host, tied to the USB port of its cable.

    Attributes
    ----------
    id : str
        The name of this physical board, for example `de0-cv-ws`.
    board : str
        The board it is, an identifier of the board packages.
    usb_path : str or None
        The stable path of the USB port (`ID_PATH` of udev).
    lock_file : str or None
        A lock file in place of the derived one.
    """

    id: str
    board: str
    usb_path: str | None = None
    lock_file: str | None = None


@dataclass(frozen=True)
class Inventory:
    """The boards of a host and where its locks live.

    Attributes
    ----------
    host : str
        The label of the host, in the name of the lock files.
    lock_dir : Path
        The directory of the lock files.
    entries : tuple of InventoryEntry
        The boards.
    """

    host: str
    lock_dir: Path
    entries: tuple[InventoryEntry, ...] = ()

    def by_id(self, ident: str) -> InventoryEntry | None:
        """Find an entry by its id.

        Parameters
        ----------
        ident : str
            The id.

        Returns
        -------
        InventoryEntry or None
            The entry, or None.
        """
        return next((e for e in self.entries if e.id == ident), None)

    def by_port(self, usb_path: str | None) -> InventoryEntry | None:
        """Find the entry of a USB port.

        Parameters
        ----------
        usb_path : str or None
            The stable path of the port.

        Returns
        -------
        InventoryEntry or None
            The entry, or None (also when the path is None).
        """
        if usb_path is None:
            return None
        return next((e for e in self.entries if e.usb_path == usb_path), None)

    def lock_path(self, board: str, entry: InventoryEntry | None) -> Path:
        """Give the lock file of a board.

        The name is the identifier without hyphens plus the host
        (`de0cv-ws.lock`), the one the boards already use, unless the
        host has two boards of the same kind, which then take their id.

        Parameters
        ----------
        board : str
            The board identifier.
        entry : InventoryEntry or None
            The entry of the physical board, when there is one.

        Returns
        -------
        Path
            The lock file.
        """
        if entry is not None and entry.lock_file:
            return Path(entry.lock_file)
        twins = [e for e in self.entries if e.board == board]
        if entry is not None and len(twins) > 1:
            return self.lock_dir / f"{entry.id}.lock"
        return self.lock_dir / f"{board.replace('-', '')}-{self.host}.lock"


def default_host() -> str:
    """Return the label of this host.

    Returns
    -------
    str
        `RISCV_TOOLS_HOST` when set, else the short hostname.
    """
    return (
        os.environ.get("RISCV_TOOLS_HOST")
        or socket.gethostname().split(".")[0]
    )


def _entry(raw: Any) -> InventoryEntry:
    """Read one element of `boards`."""
    if not isinstance(raw, dict) or "id" not in raw or "board" not in raw:
        raise BoardError("inventory: every board needs `id` and `board`")
    item = cast(dict[str, Any], raw)
    path, lock = item.get("usb_path"), item.get("lock_file")
    return InventoryEntry(
        str(item["id"]),
        str(item["board"]),
        None if path is None else str(path),
        None if lock is None else str(lock),
    )


def parse_inventory(data: Any, host: str | None = None) -> Inventory:
    """Build an Inventory from the parsed file.

    Parameters
    ----------
    data : Any
        The parsed YAML, or None for an empty file.
    host : str, optional
        The label of the host in place of the file's and the default.

    Returns
    -------
    Inventory
        The inventory.

    Raises
    ------
    BoardError
        The file is malformed or repeats an id or a port.
    """
    doc = cast(dict[str, Any], data or {})
    entries = tuple(_entry(e) for e in doc.get("boards", []))
    ids = [e.id for e in entries]
    ports = [e.usb_path for e in entries if e.usb_path]
    if len(set(ids)) != len(ids) or len(set(ports)) != len(ports):
        raise BoardError("inventory: an id or a usb_path appears twice")
    return Inventory(
        host or str(doc.get("host") or default_host()),
        Path(str(doc.get("lock_dir", DEFAULT_LOCK_DIR))),
        entries,
    )


def load_inventory(
    path: Path | None = None, host: str | None = None
) -> Inventory:
    """Read the inventory of the host.

    Parameters
    ----------
    path : Path, optional
        The file; without it the user's, then the system's.
    host : str, optional
        The label of the host, overriding the file's.

    Returns
    -------
    Inventory
        The inventory, empty when there is no file.
    """
    candidates: list[Path] = (
        [path] if path else [USER_FILE.expanduser(), SYSTEM_FILE]
    )
    for candidate in candidates:
        if candidate.is_file():
            data = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            return parse_inventory(data, host)
    return parse_inventory({}, host)


def dump_inventory(inventory: Inventory) -> str:
    """Write the inventory as YAML.

    Parameters
    ----------
    inventory : Inventory
        The inventory.

    Returns
    -------
    str
        The text of the file.
    """
    boards: list[dict[str, str]] = []
    for e in inventory.entries:
        row = {"id": e.id, "board": e.board}
        if e.usb_path:
            row["usb_path"] = e.usb_path
        if e.lock_file:
            row["lock_file"] = e.lock_file
        boards.append(row)
    doc = {
        "host": inventory.host,
        "lock_dir": str(inventory.lock_dir),
        "boards": boards,
    }
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)
