"""Read-only views of the USB bus and of the processes of the host.

Both are injected into the callers as plain functions so that the tests
feed fixtures instead of the real host.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

USB_BLASTER = "09fb:6001"
USB_BLASTER_II_COLD = "09fb:6010"
USB_BLASTER_II_WARM = "09fb:6810"
ARDUINO_MKR_VIDOR = "2341:8056"

_LSUSB = re.compile(
    r"^Bus (\d+) Device (\d+): ID ([0-9a-f]{4}:[0-9a-f]{4})\s*(.*)$"
)
_QUARTUS_USERS = ("quartus_pgm", "quartus_stp")
_SYS_USB = Path("/sys/bus/usb/devices")


@dataclass(frozen=True)
class UsbDevice:
    """One line of `lsusb`.

    Attributes
    ----------
    ident : str
        The `vendor:product` pair in lower case.
    description : str
        The text `lsusb` prints after it.
    """

    ident: str
    description: str


def parse_lsusb(text: str) -> list[UsbDevice]:
    """Parse the output of `lsusb`.

    Parameters
    ----------
    text : str
        The standard output of `lsusb`.

    Returns
    -------
    list of UsbDevice
        One per device line, in the order printed.
    """
    found: list[UsbDevice] = []
    for line in text.splitlines():
        match = _LSUSB.match(line.strip())
        if match:
            found.append(UsbDevice(match.group(3), match.group(4).strip()))
    return found


def read_usb() -> list[UsbDevice]:
    """Run `lsusb`.

    Returns
    -------
    list of UsbDevice
        The devices, or none when `lsusb` is not installed.
    """
    if shutil.which("lsusb") is None:
        return []
    out = subprocess.run(
        ["lsusb"], check=False, capture_output=True, text=True
    )
    return parse_lsusb(out.stdout)


def port_path(bus_port: str) -> str | None:
    """Return the stable path of the USB port a device sits on.

    The `ID_PATH` of udev (`pci-0000:00:14.0-usb-0:2`) names the
    physical port, so it survives a reboot and a renumbering of the
    `<bus>-<port>` of the cable name. Without `udevadm`, the position
    of the device in `/sys/devices` serves, with the prefix `sys:`.

    Parameters
    ----------
    bus_port : str
        The `1-2` of `USB-Blaster [1-2]`.

    Returns
    -------
    str or None
        The path, or None when the device is not in sysfs.
    """
    node = _SYS_USB / bus_port
    if not node.exists():
        return None
    if shutil.which("udevadm") is not None:
        out = subprocess.run(
            ["udevadm", "info", "-q", "property", "-p", str(node)],
            check=False,
            capture_output=True,
            text=True,
        ).stdout
        for line in out.splitlines():
            if line.startswith("ID_PATH="):
                return line.removeprefix("ID_PATH=")
    return "sys:" + str(node.resolve()).removeprefix("/sys/devices/")


def _argv(entry: Path) -> list[str]:
    """Read the command line of a /proc entry, empty when unreadable."""
    try:
        raw = (entry / "cmdline").read_bytes()
    except OSError:
        return []
    return [a for a in raw.decode(errors="replace").split("\0") if a]


def list_cable_users() -> list[tuple[int, str]]:
    """List the processes that use a JTAG cable.

    Returns
    -------
    list of tuple of (int, str)
        The pid and command line of every process whose program is one
        of the Quartus tools that open the cable, except this one.
    """
    users: list[tuple[int, str]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        argv = _argv(entry)
        if argv and Path(argv[0]).name in _QUARTUS_USERS:
            users.append((int(entry.name), " ".join(argv)))
    return sorted(users)
