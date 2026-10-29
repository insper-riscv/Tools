"""The host side of the seven-segment display register of the platform.

The six digits of the display are a 24-bit register that the program or the host
writes (see Memory's seg_display). This module reads and writes it through the
Virtual JTAG instance of the register. Pure mechanism, no policy.
"""

import subprocess

from riscv_tools.jtag import JtagLink
from riscv_tools.jtag.link import TCL_DIR

VALUE_PREFIX = "VALUE="
FLAG_PREFIX = "FLAG="
CHECK_PREFIX = "CHECKED="
MAX_VALUE = 0xFFFFFF
# HEX5 and HEX4 read "AC" while the ELFs of the ACT4 run
ACT_PREFIX = 0xAC0000
MAX_ACT_NUMBER = 9999
MAX_TEST_NUMBER = 999999


def _decimal_digits(number: int) -> int:
    """Write the decimal digits of number as hexadecimal digits: 59 becomes 0x59."""
    return int(str(number), 16)


def encode_act(number: int) -> int:
    """Value of the register while the ELF number of an ACT4 run executes.

    HEX5 and HEX4 show ``A`` and ``C``; HEX3 to HEX0 show the number in decimal,
    so the first ELF reads ``AC0001`` and the 59th ``AC0059``.

    Parameters
    ----------
    number : int
        Position of the ELF in the session, counted from 1.

    Returns
    -------
    int
        The register value.

    Raises
    ------
    ValueError
        The number is not between 1 and 9999.
    """
    if not 1 <= number <= MAX_ACT_NUMBER:
        raise ValueError(
            f"the ELF number {number} is not between 1 and {MAX_ACT_NUMBER}"
        )
    return ACT_PREFIX | _decimal_digits(number)


def encode_test(number: int) -> int:
    """Value of the register while the number-th program of the own suite executes.

    The six digits show the number in decimal: ``000001`` to ``999999``.

    Parameters
    ----------
    number : int
        Position of the program in the session, counted from 1.

    Returns
    -------
    int
        The register value.

    Raises
    ------
    ValueError
        The number is not between 1 and 999999.
    """
    if not 1 <= number <= MAX_TEST_NUMBER:
        raise ValueError(
            f"the test number {number} is not between 1 and {MAX_TEST_NUMBER}"
        )
    return _decimal_digits(number)


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


def _run_fail(link: JtagLink, action: str) -> bool:
    """Run display.tcl in fail mode (read, set or clear) and return the flag."""
    cmd = [
        "quartus_stp",
        "-t",
        str(TCL_DIR / "display.tcl"),
        link.hardware_name,
        link.device_name,
        "fail",
        action,
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"display.tcl failed ({done.returncode}): {done.stderr}")
    for raw in reversed(done.stdout.splitlines()):
        line = raw.strip()
        if line.startswith(FLAG_PREFIX):
            return line[len(FLAG_PREFIX) :] == "1"
    raise RuntimeError(f"the display script printed no flag: {done.stdout!r}")


def read_fail(link: JtagLink) -> bool:
    """Read the failure flag that the board shows on its first red LED.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.

    Returns
    -------
    bool
        True when the flag is set.
    """
    return _run_fail(link, "read")


def write_fail(link: JtagLink, failed: bool) -> bool:
    """Set or clear the failure flag and read it back.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    failed : bool
        True to set the flag (the LED lights), False to clear it.

    Returns
    -------
    bool
        What the flag holds after the write.
    """
    return _run_fail(link, "set" if failed else "clear")
