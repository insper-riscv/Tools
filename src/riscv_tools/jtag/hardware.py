"""Live detection of the connected JTAG cable's hardware name."""

import re
import subprocess


def detect_jtag_hardware() -> str:
    """Detect the live JTAG hardware name for the -c flag of Quartus.

    The name suffix reflects USB topology, not the physical cable, and
    drifts across reboots, so it is read from `jtagconfig` instead of
    the config. Only a "USB-Blaster" entry is taken, since another
    board's cable can appear in the same listing.

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
    for line in out.splitlines():
        m = re.match(r"^\s*\d+\)\s+(USB-Blaster.*)$", line)
        if m:
            return m.group(1).strip()
    raise RuntimeError(
        f"jtagconfig produced no USB-Blaster hardware line:\n{out}"
    )


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
