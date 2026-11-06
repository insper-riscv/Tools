"""The checks of `board doctor`: cable, chain and processes.

Nothing here changes the host. Each check says what it found and, when
something is missing, what to do about it; the commands that fix a
problem are suggested, never run.
"""

from dataclasses import dataclass

from riscv_tools.board.lock import read_owner
from riscv_tools.board.scan import CableReport
from riscv_tools.board.select import Environment
from riscv_tools.board.usb import (
    ARDUINO_MKR_VIDOR,
    USB_BLASTER_II_COLD,
    USB_BLASTER_II_WARM,
    UsbDevice,
)

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class Check:
    """The result of one check.

    Attributes
    ----------
    name : str
        What was checked.
    level : str
        `ok`, `warn` or `fail`.
    detail : str
        What was found.
    hint : str
        What to do, empty when `ok`.
    """

    name: str
    level: str
    detail: str
    hint: str = ""


def _cable_checks(report: CableReport) -> list[Check]:
    """Check the chain and the identification of one cable."""
    name = report.cable.name
    if report.cable.broken:
        return [
            Check(
                f"chain of {name}",
                FAIL,
                str(report.cable.error),
                "case 8: power the board off for about 10 s and on again; "
                "if it persists, `killall jtagd` once and read the chain "
                "again",
            )
        ]
    checks = [Check(f"chain of {name}", OK, _chain_text(report))]
    label = ", ".join(report.boards)
    if report.problem:
        checks.append(Check(f"identity of {name}", FAIL, report.problem))
    elif len(report.boards) > 1:
        checks.append(
            Check(
                f"identity of {name}",
                WARN,
                f"may be {', '.join(report.boards)}",
                "register the port in the inventory with "
                "`riscv-tools board scan --save --assign PORT=BOARD`",
            )
        )
    elif report.port is None:
        checks.append(
            Check(
                f"identity of {name}",
                OK,
                f"{label} (no USB port path to register)",
            )
        )
    else:
        checks.append(
            Check(
                f"identity of {name}",
                OK,
                f"{label} at {report.port}",
            )
        )
    return checks


def _chain_text(report: CableReport) -> str:
    """Write the chain of a cable as `IDCODE name` pairs."""
    return ", ".join(f"{d.idcode} {d.name}" for d in report.cable.devices)


def _entry_checks(env: Environment, ports: set[str | None]) -> list[Check]:
    """Check each inventory entry: cable present, lock owner."""
    checks: list[Check] = []
    for entry in env.inventory.entries:
        lock = env.inventory.lock_path(entry.board, entry)
        if entry.usb_path not in ports:
            checks.append(
                Check(
                    f"inventory {entry.id}",
                    WARN,
                    f"no cable at {entry.usb_path}",
                    "plug the board into its port and power it, or update "
                    "the inventory",
                )
            )
        if not env.lock_free(lock):
            owner = read_owner(lock)
            who = (
                f"{owner.user}@{owner.host}: {owner.command}" if owner else "?"
            )
            checks.append(Check(f"lock of {entry.id}", OK, f"held by {who}"))
    return checks


def _inventory_checks(
    env: Environment, reports: list[CableReport]
) -> list[Check]:
    """Compare the inventory with the cables and show the locks."""
    checks = _entry_checks(env, {r.port for r in reports})
    checks.extend(
        Check(
            f"inventory for {report.cable.name}",
            WARN,
            f"port {report.port} ({report.boards[0]}) is not registered",
            "run `riscv-tools board scan --save`",
        )
        for report in reports
        if report.entry is None and report.port and len(report.boards) == 1
    )
    return checks


def _usb_checks(env: Environment, usb: list[UsbDevice]) -> list[Check]:
    """Check the boards that need more than a USB-Blaster."""
    ids = {d.ident for d in usb}
    checks: list[Check] = []
    if ARDUINO_MKR_VIDOR in ids and not any(
        env.boards[b].cable == "samd21-usbblaster"
        for r in env.reports()
        for b in r.candidates
    ):
        checks.append(
            Check(
                "MKR Vidor 4000",
                WARN,
                f"{ARDUINO_MKR_VIDOR} is on the USB, but no JTAG cable "
                "answers through it",
                "load the USBBlaster sketch of the Arduino core into the "
                "SAMD21 (the tools do not write it), then read the chain "
                "again; the sketch must run for the emulated USB-Blaster to "
                "show up",
            )
        )
    if USB_BLASTER_II_COLD in ids:
        checks.append(
            Check(
                "USB-Blaster II",
                WARN,
                f"{USB_BLASTER_II_COLD} (firmware not loaded yet)",
                "run `jtagconfig` once so jtagd loads the firmware; the "
                f"device then reappears as {USB_BLASTER_II_WARM}",
            )
        )
    if USB_BLASTER_II_WARM in ids and not any(
        c.name.lower().startswith("de-soc") for c in env.cables
    ):
        checks.append(
            Check(
                "DE10-Nano cable",
                WARN,
                f"{USB_BLASTER_II_WARM} is on the USB but jtagconfig lists "
                "no DE-SoC cable",
                "power the board before plugging the USB cable, and check "
                "that jtagd runs as the user that owns the device",
            )
        )
    return checks


def _hps_checks(env: Environment) -> list[Check]:
    """Suggest the chain setup when the HPS is in it (error 209025)."""
    checks: list[Check] = []
    for cable in env.cables:
        has_hps = any(d.idcode == "4BA00477" for d in cable.devices)
        if has_hps and len(cable.devices) > 1:
            checks.append(
                Check(
                    f"HPS in the chain of {cable.name}",
                    WARN,
                    "the ARM DAP (4BA00477) shares the chain with the FPGA",
                    "if the programmer fails with error 209025, remove the "
                    "HPS from the chain in the Quartus programmer (this "
                    "command does not change it)",
                )
            )
    return checks


def missing_tool() -> Check:
    """Build the check for a host without `jtagconfig`.

    Returns
    -------
    Check
        A failure that says how to get the tool.
    """
    return Check(
        "jtagconfig",
        FAIL,
        "not found on the PATH",
        "install Quartus and put its bin directory on the PATH",
    )


def run_doctor(
    env: Environment,
    usb: list[UsbDevice],
    users: list[tuple[int, str]],
) -> list[Check]:
    """Run every check of the host.

    Parameters
    ----------
    env : Environment
        The host as the selection sees it.
    usb : list of UsbDevice
        The devices `lsusb` listed.
    users : list of tuple of (int, str)
        The processes that use a cable (pid, command line).

    Returns
    -------
    list of Check
        The results, in the order of the checks.
    """
    reports = env.reports()
    checks = [Check("jtagconfig", OK, f"{len(env.cables)} cable(s) listed")]
    if not env.cables:
        checks.append(
            Check(
                "cables",
                FAIL,
                "jtagconfig lists no cable",
                "check the USB cable, the power of the board and that jtagd "
                "runs",
            )
        )
    for report in reports:
        checks += _cable_checks(report)
    checks += _inventory_checks(env, reports)
    checks += _usb_checks(env, usb) + _hps_checks(env)
    for pid, command in users:
        checks.append(
            Check(
                f"process {pid}",
                WARN,
                command,
                "a Quartus tool that opens the cable is running; a second "
                "access can hang both (case 9)",
            )
        )
    return checks
