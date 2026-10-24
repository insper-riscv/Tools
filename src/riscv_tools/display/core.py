"""The host side of the seven-segment display register of the platform.

The six digits of the display are a 24-bit register that the program or the host
writes (see Memory's seg_display). This module reads and writes it through the
Virtual JTAG instance of the register. Pure mechanism, no policy.
"""

import subprocess

from riscv_tools.jtag import JtagLink
from riscv_tools.jtag.link import TCL_DIR

VALUE_PREFIX = "VALUE="
CHECK_PREFIX = "CHECKED="
MAX_VALUE = 0xFFFFFF
MAX_INDEX = 0xFF
MAX_STATE = 0xFFFF
STATE_RUNNING = 0x0000
STATE_PASSED = 0x0001
STATE_FAILED = 0x000F


def encode_state(index: int, state: int) -> int:
    """Pack the ELF index and its state into the 24-bit value of the register.

    Parameters
    ----------
    index : int
        Index of the ELF in the session, 0 to 255 (digits HEX5 and HEX4).
    state : int
        State, 0 to 0xFFFF (digits HEX3 to HEX0).

    Returns
    -------
    int
        The register value.

    Raises
    ------
    ValueError
        The index or the state does not fit in its digits.
    """
    if not 0 <= index <= MAX_INDEX:
        raise ValueError(f"the index {index} does not fit in two digits")
    if not 0 <= state <= MAX_STATE:
        raise ValueError(f"the state {state} does not fit in four digits")
    return (index << 16) | state


def decode_value(output: str) -> int:
    """Find the register value in the output of the script.

    Parameters
    ----------
    output : str
        Everything the script printed.

    Returns
    -------
    int
        The value of the last ``VALUE=<hex digits>`` line.

    Raises
    ------
    RuntimeError
        The output has no such line.
    """
    for raw in reversed(output.splitlines()):
        line = raw.strip()
        if line.startswith(VALUE_PREFIX):
            return int(line[len(VALUE_PREFIX) :], 16)
    raise RuntimeError(f"the display script printed no value: {output!r}")


def _run(link: JtagLink, *args: str) -> int:
    """Run display.tcl with args and return the value it reports."""
    cmd = [
        "quartus_stp",
        "-t",
        str(TCL_DIR / "display.tcl"),
        link.hardware_name,
        link.device_name,
        *args,
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"display.tcl failed ({done.returncode}): {done.stderr}")
    return decode_value(done.stdout)


def check_display(link: JtagLink, count: int) -> int:
    """Write count pseudo-random values and read each back.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    count : int
        How many values to write.

    Returns
    -------
    int
        How many reads differed from what was written.

    Raises
    ------
    RuntimeError
        The script failed or printed no result.
    """
    cmd = [
        "quartus_stp",
        "-t",
        str(TCL_DIR / "display.tcl"),
        link.hardware_name,
        link.device_name,
        "check",
        str(count),
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"display.tcl failed ({done.returncode}): {done.stderr}")
    for line in done.stdout.splitlines():
        if line.startswith(CHECK_PREFIX):
            return int(line.rsplit("=", 1)[1])
    raise RuntimeError(f"the display script printed no result: {done.stdout!r}")


def read_display(link: JtagLink) -> int:
    """Read the register.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.

    Returns
    -------
    int
        The 24-bit value.
    """
    return _run(link, "read")


def write_display(link: JtagLink, value: int) -> int:
    """Write the register and read it back.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    value : int
        The 24-bit value to show.

    Returns
    -------
    int
        What the register holds after the write.

    Raises
    ------
    ValueError
        The value does not fit in 24 bits.
    """
    if not 0 <= value <= MAX_VALUE:
        raise ValueError(f"the value {value} does not fit in 24 bits")
    return _run(link, "write", f"{value:06x}")
