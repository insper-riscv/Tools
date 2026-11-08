"""Live reading of `jtagconfig`: every cable and the chain behind it."""

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

_CABLE_LINE = re.compile(r"^\s*\d+\)\s+(\S.*?)\s*$")
_DEVICE_LINE = re.compile(r"^\s+([0-9A-Fa-f]{8})\s+(\S.*?)\s*$")
_BUS_PORT = re.compile(r"\[(\d+-[\d.]+)\]\s*$")
_IDCODE = re.compile(r"0x([0-9A-Fa-f]{8})")
_VERSION_MASK = 0x0FFFFFFF


@dataclass(frozen=True)
class ChainDevice:
    """One device of a JTAG chain, as `jtagconfig` prints it.

    Attributes
    ----------
    position : int
        1-based position in the chain, the `@N` of the Quartus
        device identity.
    idcode : str
        The IDCODE in upper case, eight hex digits.
    name : str
        The name pattern `jtagconfig` prints beside the IDCODE.
    """

    position: int
    idcode: str
    name: str

    @property
    def identity(self) -> str:
        """Return the Quartus device identity of the device.

        Returns
        -------
        str
            The `@N: name (0xIDCODE)` string that Quartus takes as
            `-device_name`, the same form as `quartus.jtag_device`.
        """
        return f"@{self.position}: {self.name} (0x{self.idcode})"


@dataclass(frozen=True)
class Cable:
    """One cable listed by `jtagconfig` and the chain behind it.

    Attributes
    ----------
    name : str
        The cable name, for example `USB-Blaster [1-2]` or
        `DE-SoC [USB-1]`; it drifts across reboots, so it only
        serves as the `-c` argument of one session.
    devices : tuple of ChainDevice
        The devices of the chain, in order; empty when the chain
        could not be read.
    error : str or None
        The text `jtagconfig` printed instead of a chain (for example
        `Unable to read device chain - JTAG chain broken`), or None.
    """

    name: str
    devices: tuple[ChainDevice, ...]
    error: str | None = None

    @property
    def broken(self) -> bool:
        """Tell whether the chain of the cable is reported broken.

        Returns
        -------
        bool
            True when `jtagconfig` printed an error for this cable.
        """
        return self.error is not None

    @property
    def bus_port(self) -> str | None:
        """Return the `<bus>-<port>` of a cable named `Name [bus-port]`.

        Returns
        -------
        str or None
            The `1-2` of `USB-Blaster [1-2]`, or None for a name
            without it (the USB-Blaster II prints `DE-SoC [USB-1]`).
        """
        found = _BUS_PORT.search(self.name)
        return found.group(1) if found else None


def idcode_of(device_name: str | None) -> str | None:
    """Pull the JTAG IDCODE out of a device identity string.

    Parameters
    ----------
    device_name : str or None
        The `quartus.jtag_device` of the config, for example
        `@1: 5CE(BA4|FA4) (0x02B050DD)`.

    Returns
    -------
    str or None
        The IDCODE in upper case (`02B050DD`), or None when the string
        has none.
    """
    found = _IDCODE.search(device_name or "")
    return found.group(1).upper() if found else None


def same_idcode(left: str, right: str) -> bool:
    """Compare two IDCODEs without the 4 bits of version.

    Parameters
    ----------
    left, right : str
        IDCODEs of eight hex digits, in any case.

    Returns
    -------
    bool
        True when they are equal ignoring the version field that IEEE
        1149.1 reserves in the top 4 bits of every IDCODE.
    """
    return (int(left, 16) & _VERSION_MASK) == (int(right, 16) & _VERSION_MASK)


def _cable(name: str, body: list[str]) -> Cable:
    """Build a cable from its header name and the lines under it."""
    devices: list[ChainDevice] = []
    errors: list[str] = []
    for line in body:
        device = _DEVICE_LINE.match(line)
        if device:
            devices.append(
                ChainDevice(
                    len(devices) + 1,
                    device.group(1).upper(),
                    device.group(2),
                )
            )
        elif line.strip():
            errors.append(line.strip())
    return Cable(name, tuple(devices), " ".join(errors) or None)


def parse_jtagconfig(text: str) -> list[Cable]:
    """Parse the output of `jtagconfig` into every cable listed.

    Parameters
    ----------
    text : str
        The standard output of `jtagconfig`.

    Returns
    -------
    list of Cable
        One entry per `N) <cable>` line, in the order printed. A line
        under a cable that is not a device (the "chain broken" and
        "unable to lock" messages) becomes the `error` of the cable.
    """
    blocks: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        header = _CABLE_LINE.match(line)
        if header:
            blocks.append((header.group(1), []))
        elif blocks:
            blocks[-1][1].append(line)
    return [_cable(name, body) for name, body in blocks]


def _run_jtagconfig(*, check: bool) -> subprocess.CompletedProcess[str]:
    """Run `jtagconfig` once, capturing its output as text."""
    return subprocess.run(
        ["jtagconfig"], check=check, capture_output=True, text=True
    )


def read_cables() -> list[Cable]:
    """Run `jtagconfig` and list every cable with its chain.

    This is the only reading of `jtagconfig` of the whole project:
    the cable choice, the board identification and the diagnostics
    all go through it.

    Returns
    -------
    list of Cable
        Every cable, possibly none.

    Raises
    ------
    subprocess.CalledProcessError
        `jtagconfig` ran and failed.
    """
    return parse_jtagconfig(_run_jtagconfig(check=True).stdout)


def _forced(cables: list[Cable], name: str, wanted: str | None) -> str:
    """Check a cable forced by name and return it."""
    found = next((c for c in cables if c.name == name), None)
    if found is None:
        listed = ", ".join(c.name for c in cables)
        raise RuntimeError(f"cable {name!r} not listed; cables: {listed}")
    if wanted and not any(
        same_idcode(d.idcode, wanted) for d in found.devices
    ):
        raise RuntimeError(f"cable {name!r} does not list the IDCODE {wanted}")
    return found.name


def _with_idcode(cables: Sequence[Cable], wanted: str | None) -> str | None:
    """Return the first cable whose chain lists the IDCODE, if any."""
    if not wanted:
        return None
    for listed in cables:
        if any(same_idcode(d.idcode, wanted) for d in listed.devices):
            return listed.name
    return None


def detect_jtag_hardware(
    device_name: str | None = None, cable: str | None = None
) -> str:
    """Detect the live JTAG hardware name for the -c flag of Quartus.

    The name suffix reflects USB topology, not the physical cable, and
    drifts across reboots, so it is read from `jtagconfig` instead of
    the config. A machine with several cables (the workstation has
    four FPGAs) is told apart by the IDCODE of the chip on each cable:
    with `device_name` the cable whose chain lists that IDCODE is the
    one returned. The board identification of `riscv_tools.board`
    builds on `read_cables` and adds the USB port to this choice.

    Parameters
    ----------
    device_name : str, optional
        The chip identity of the project (`quartus.jtag_device`); its
        IDCODE chooses the cable. Without it, or when no cable lists
        the IDCODE, the first cable is taken.

    cable : str, optional
        A cable name forced by the caller (`--cable`): it must be
        listed and, with `device_name`, its chain must list the IDCODE.

    Returns
    -------
    str
        The full cable name, for example "USB-Blaster [<bus>-<port>]",
        as `jtagconfig` currently reports it.

    Raises
    ------
    RuntimeError
        `jtagconfig`'s output has no cable line (cable unplugged,
        driver not loaded, etc), or a forced cable is not listed or
        lacks the IDCODE.
    """
    cables = read_cables()
    if not cables:
        raise RuntimeError("jtagconfig produced no cable line")
    wanted = idcode_of(device_name)
    if cable is not None:
        return _forced(cables, cable, wanted)
    return _with_idcode(cables, wanted) or cables[0].name


def jtag_chain_healthy() -> bool:
    """Check whether `jtagconfig` reports a working device chain.

    detect_jtag_hardware can find the cable while the chain beneath it
    is broken, because "chain broken" is a separate line of the
    `jtagconfig` output. Meant for polling after a physical power-cycle.

    Returns
    -------
    bool
        False if `jtagconfig` reports "chain broken" (case-insensitive)
        anywhere in its output, or if `jtagconfig` itself fails to run
        at all (cable unplugged, driver issue, etc, treated as
        "still not healthy" rather than raising, since this is meant
        to be polled in a loop). True otherwise.
    """
    try:
        out = _run_jtagconfig(check=False)
    except FileNotFoundError:
        return False
    text = f"{out.stdout}\n{out.stderr}".lower()
    return "chain broken" not in text
