import re
import subprocess


def detect_jtag_hardware() -> str:
    """Returns the live "USB-Blaster [<bus>-<port>]" hardware name for
    quartus_pgm/quartus_stp's -c/-hardware_name flags.

    That suffix reflects USB topology, not the physical cable — it
    drifts across reboots and hub renumbering, so a static config value
    is unreliable; ask `jtagconfig` for the live value instead.

    Matched specifically on "USB-Blaster" rather than just taking the
    first hardware line: a second cable (e.g. another board's onboard
    blaster) can show up in the same jtagconfig listing when another
    board is plugged into the same workstation, and it isn't ours.

    Returns:
        The full "USB-Blaster [<bus>-<port>]" hardware name, as
        `jtagconfig` currently reports it.

    Raises:
        RuntimeError: `jtagconfig`'s output has no USB-Blaster line
            (cable unplugged, driver not loaded, etc).
    """
    out = subprocess.run(["jtagconfig"], check=True, capture_output=True, text=True).stdout
    for line in out.splitlines():
        m = re.match(r"^\s*\d+\)\s+(USB-Blaster.*)$", line)
        if m:
            return m.group(1).strip()
    raise RuntimeError(f"jtagconfig produced no USB-Blaster hardware line:\n{out}")
