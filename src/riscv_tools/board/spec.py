"""What the tools know about a board: the `jtag` part of `board.yaml`.

The identification only needs the name of the board, its device and the
JTAG chain it presents, so only these fields are read. Every other field
of the file belongs to the generators and the validator.

```yaml
board: de0-cv
device: 5CEBA4F23C7
jtag:
  cable: usb-blaster   # usb-blaster-ii, samd21-usbblaster, external
  chain: [{name: "5CE(BA4|FA4)", idcode: "02B050DD", fpga: true}]
```
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.board.errors import BoardError

IDCODE_DIGITS = 8
CABLE_KINDS = frozenset(
    {"usb-blaster", "usb-blaster-ii", "samd21-usbblaster", "external"}
)


@dataclass(frozen=True)
class ExpectedDevice:
    """One device the chain of a board must present.

    Attributes
    ----------
    name : str
        The pattern `jtagconfig` prints beside the IDCODE.
    idcode : str
        The IDCODE in upper case, eight hex digits.
    fpga : bool
        True for the FPGA (the HPS of the DE10-Nano is the other one).
    """

    name: str
    idcode: str
    fpga: bool = False


@dataclass(frozen=True)
class BoardSpec:
    """The identification data of a board.

    Attributes
    ----------
    board : str
        The identifier (`de0-cv`).
    device : str or None
        The full device (`5CEBA4F23C7`), which the IDCODE alone does
        not prove.
    cable : str
        The kind of cable, one of CABLE_KINDS.
    chain : tuple of ExpectedDevice
        The devices of the chain, in order.
    """

    board: str
    device: str | None
    cable: str
    chain: tuple[ExpectedDevice, ...]

    @property
    def fpga(self) -> ExpectedDevice:
        """Return the FPGA device of the chain.

        Returns
        -------
        ExpectedDevice
            The element marked `fpga`, or the only one.
        """
        marked = [d for d in self.chain if d.fpga]
        return marked[0] if marked else self.chain[-1]


def adhoc_board(idcode: str, name: str = "adhoc") -> BoardSpec:
    """Make a board known only by the IDCODE of its FPGA.

    For a board that has no `board.yaml` yet, selected with `--idcode`.

    Parameters
    ----------
    idcode : str
        The IDCODE of the FPGA, eight hex digits.
    name : str
        The name to give the board.

    Returns
    -------
    BoardSpec
        A board with one FPGA device and a USB-Blaster.
    """
    device = ExpectedDevice("", idcode.upper(), fpga=True)
    return BoardSpec(name, None, "usb-blaster", (device,))


def _device(raw: Any, board: str) -> ExpectedDevice:
    """Read one `jtag.chain` element."""
    if not isinstance(raw, dict) or "idcode" not in raw:
        raise BoardError(f"{board}: jtag.chain element without idcode")
    item = cast(dict[str, Any], raw)
    idcode = str(item["idcode"]).upper().removeprefix("0X")
    if len(idcode) != IDCODE_DIGITS or any(
        c not in "0123456789ABCDEF" for c in idcode
    ):
        raise BoardError(f"{board}: idcode {idcode!r} is not 8 hex digits")
    return ExpectedDevice(
        str(item.get("name", "")), idcode, bool(item.get("fpga", False))
    )


def parse_board(data: Any, source: str) -> BoardSpec:
    """Build a BoardSpec from the parsed `board.yaml`.

    Parameters
    ----------
    data : Any
        The parsed YAML document.
    source : str
        Where it came from, for the error messages.

    Returns
    -------
    BoardSpec
        The identification data of the board.

    Raises
    ------
    BoardError
        A required field is missing or malformed.
    """
    if not isinstance(data, dict) or "board" not in data:
        raise BoardError(f"{source}: no `board` field")
    doc = cast(dict[str, Any], data)
    jtag = doc.get("jtag")
    if not isinstance(jtag, dict):
        raise BoardError(f"{source}: no `jtag.chain`")
    jtag_doc = cast(dict[str, Any], jtag)
    if not jtag_doc.get("chain"):
        raise BoardError(f"{source}: no `jtag.chain`")
    cable = str(jtag_doc.get("cable", "usb-blaster"))
    if cable not in CABLE_KINDS:
        raise BoardError(f"{source}: jtag.cable {cable!r} is not known")
    board = str(doc["board"])
    chain = tuple(_device(d, board) for d in jtag_doc["chain"])
    device = doc.get("device")
    return BoardSpec(
        board, None if device is None else str(device), cable, chain
    )


def load_boards(directories: list[Path]) -> dict[str, BoardSpec]:
    """Read every `<directory>/<board>/board.yaml`.

    Parameters
    ----------
    directories : list of Path
        The directories that hold the board packages; a missing one is
        skipped, and a board found twice keeps the first.

    Returns
    -------
    dict of {str: BoardSpec}
        The known boards by identifier, sorted by it.
    """
    found: dict[str, BoardSpec] = {}
    for directory in directories:
        for path in sorted(directory.glob("*/board.yaml")):
            spec = parse_board(
                yaml.safe_load(path.read_text(encoding="utf-8")), str(path)
            )
            found.setdefault(spec.board, spec)
    return dict(sorted(found.items()))
