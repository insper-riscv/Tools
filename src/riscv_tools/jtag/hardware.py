"""Live detection of the connected JTAG cable's hardware name."""

import re
import subprocess

_CABLE = re.compile(r"^\s*\d+\)\s+(USB-Blaster.*)$")


_ANY_CABLE = re.compile(r"^\s*\d+\)\s+\S")


_IDCODE = re.compile(r"0x([0-9A-Fa-f]{8})")


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


def detect_jtag_hardware(device_name: str | None = None) -> str:
    """Detect the live JTAG hardware name for the -c flag of Quartus.

    The name suffix reflects USB topology, not the physical cable, and
    drifts across reboots, so it is read from `jtagconfig` instead of
    the config. Only a "USB-Blaster" entry is taken. A machine with
    several cables (the workstation has four FPGAs) is told apart by
    the IDCODE of the chip on each cable: with `device_name` the cable
    whose chain lists that IDCODE is the one returned.

    Parameters
    ----------
    device_name : str, optional
        The chip identity of the project (`quartus.jtag_device`); its
        IDCODE chooses the cable. Without it, or when no cable lists
        the IDCODE, the first USB-Blaster is taken.

    Returns
    -------
    str
        The full "USB-Blaster [<bus>-<port>]" hardware name, as
        `jtagconfig` currently reports it.

    Raises
    ------
    RuntimeError
        `jtagconfig`'s output has no USB-Blaster line (cable
        unplugged, driver not loaded, etc).
    """
    out = subprocess.run(
        ["jtagconfig"], check=True, capture_output=True, text=True
    ).stdout
    wanted = idcode_of(device_name)
    cables: dict[str, str] = {}
    current: str | None = None
    for line in out.splitlines():
        found = _CABLE.match(line)
        if found:
            name = str(found.group(1)).strip()
            current = name
            cables[name] = ""
        elif _ANY_CABLE.match(line):
            current = None
        elif current is not None:
            cables[current] = cables[current] + line.upper()
    if not cables:
        raise RuntimeError(
            f"jtagconfig produced no USB-Blaster hardware line:\n{out}"
        )
    for name, chain in cables.items():
        if wanted and wanted in chain:
            return name
    return next(iter(cables))


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
        out = subprocess.run(
            ["jtagconfig"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return False
    text = f"{out.stdout}\n{out.stderr}".lower()
    return "chain broken" not in text
