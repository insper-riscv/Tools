"""Live detection of the connected JTAG cable's hardware name."""

import re
import subprocess


def detect_jtag_hardware() -> str:
    """Detect the live JTAG hardware name for quartus_pgm/quartus_stp's -c flag.

    That suffix reflects USB topology, not the physical cable — it
    drifts across reboots and hub renumbering, so a static config value
    is unreliable; ask `jtagconfig` for the live value instead.

    Matched specifically on "USB-Blaster" rather than just taking the
    first hardware line: a second cable (e.g. another board's onboard
    blaster) can show up in the same jtagconfig listing when another
    board is plugged into the same workstation, and it isn't ours.

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
    raise RuntimeError(f"jtagconfig produced no USB-Blaster hardware line:\n{out}")


def jtag_chain_healthy() -> bool:
    """Check whether `jtagconfig` currently reports a working device chain.

    Separate from detect_jtag_hardware: that one finds the cable's
    live name and can succeed even while the chain underneath it is
    broken — "chain broken" is a distinct line jtagconfig prints
    alongside/after the hardware listing, not instead of it. Same
    "chain broken" text/behavior documented in HARDWARE_PROGRAMMING.md
    and checked the same way by real.yml's own pre-flight step —
    meant for polling after a physical power-cycle, e.g.
    orchestrator.run_suite's wait_for_hardware mode.

    Returns
    -------
    bool
        False if `jtagconfig` reports "chain broken" (case-insensitive)
        anywhere in its output, or if `jtagconfig` itself fails to run
        at all (cable unplugged, driver issue, etc — treated as
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
