"""Read a board file (`boards/<board>/board.yaml`)."""

import re
from typing import Any

from riscv_tools.board_schema.fields import Section, raise_if
from riscv_tools.board_schema.model import (
    Board,
    Capacity,
    ClockInput,
    Clocks,
    Console,
    IoRole,
    Jtag,
    JtagDevice,
    MemoryDevice,
    Resources,
    UsbId,
    VideoRole,
)
from riscv_tools.board_schema.video import parse_video_role

CONFIRMATIONS = ("manual", "repo", "inferred", "measured")
LEVELS = ("N0", "N1", "N2", "N3", "N4")
CABLES = ("usb-blaster", "usb-blaster-ii", "samd21-usbblaster", "external")
GENERAL_ROLES = ("gpio", "ex_io", "hsmc", "clock_extra")
IO_ROLES = (
    "leds",
    "switches",
    "keys",
    "display",
    "video",
    "leds_green",
    *GENERAL_ROLES,
)
MEMORY_KEYS = ("sdram", "sram", "nor", "onchip_flash", "serial_flash")
ACTIVE_LEVELS = ("high", "low")
_IDCODE = re.compile(r"^[0-9A-Fa-f]{8}$")
_USB_ID = re.compile(r"^[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}$")


def _device(entry: Section) -> JtagDevice | None:
    """Read one device of the JTAG chain.

    Parameters
    ----------
    entry : Section
        The device.

    Returns
    -------
    JtagDevice or None
        The device; None when it is invalid.
    """
    name = entry.text("name")
    idcode = entry.text("idcode")
    fpga = entry.flag("fpga", required=False)
    hps = entry.flag("hps", required=False)
    confirmed = entry.text("confirmed", required=False, choices=CONFIRMATIONS)
    entry.done()
    if idcode is not None and not _IDCODE.match(idcode):
        entry.fail("idcode", "must be 8 hexadecimal digits")
    if fpga and hps:
        entry.fail("hps", "cannot be set on the FPGA")
    if name is None or idcode is None:
        return None
    return JtagDevice(name, idcode.upper(), fpga, hps, confirmed)


def _usb(jtag: Section) -> tuple[UsbId, ...]:
    """Read the USB identifiers of the cable.

    Parameters
    ----------
    jtag : Section
        The `jtag` section.

    Returns
    -------
    tuple of UsbId
        The identifiers.
    """
    found: list[UsbId] = []
    for index, item in enumerate(jtag.items("usb", required=False)):
        entry = Section(f"{jtag.label}.usb[{index}]", item, jtag.problems)
        usb_id = entry.text("id")
        state = entry.text("state", required=False)
        confirmed = entry.text("confirmed", choices=CONFIRMATIONS)
        entry.done()
        if usb_id and not _USB_ID.match(usb_id):
            entry.fail("id", "must be vid:pid in hexadecimal")
        elif usb_id and confirmed:
            found.append(UsbId(usb_id, state or "", confirmed))
    return tuple(found)


def _jtag(top: Section) -> Jtag | None:
    """Read the `jtag` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    Jtag or None
        The cable and the chain; None when the section is invalid.
    """
    jtag = top.section("jtag")
    if jtag is None:
        return None
    cable = jtag.text("cable", choices=CABLES)
    cable_name = jtag.text("cable_name", required=False)
    usb = _usb(jtag)
    # O sketch do SAMD21 e os pads externos são descrições livres.
    jtag.section("samd21", required=False)
    jtag.section("external_pads", required=False)
    devices = [
        device
        for index, item in enumerate(jtag.items("chain"))
        if (
            device := _device(
                Section(f"{jtag.label}.chain[{index}]", item, top.problems)
            )
        )
        is not None
    ]
    jtag.done()
    if sum(1 for device in devices if device.fpga) != 1:
        jtag.fail("chain", "must name exactly one FPGA (fpga: true)")
    if cable is None:
        return None
    return Jtag(cable, cable_name, tuple(devices), usb)


def _capacity(
    parent: Section, key: str, kind_key: str, total_key: str
) -> Capacity:
    """Read one capacity entry of `resources`.

    Parameters
    ----------
    parent : Section
        The `resources` section.
    key : str
        The entry (`logic`, `block_ram`, `multipliers`).
    kind_key : str
        The field that names the unit or kind (`unit` or `kind`).
    total_key : str
        The field that holds the count.

    Returns
    -------
    Capacity
        The capacity; an unknown total is None.
    """
    entry = parent.section(key)
    if entry is None:
        return Capacity("", None)
    kind = entry.text(kind_key)
    total = entry.integer(total_key, nullable=True, minimum=0)
    bits = None
    if key == "block_ram":
        bits = entry.integer("bits_per_block", minimum=1)
    entry.done()
    return Capacity(kind or "", total, bits)


def _resources(top: Section) -> Resources | None:
    """Read the `resources` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    Resources or None
        The capacities; None when the section is missing.
    """
    res = top.section("resources")
    if res is None:
        return None
    logic = _capacity(res, "logic", "unit", "total")
    block = _capacity(res, "block_ram", "kind", "blocks")
    mult = _capacity(res, "multipliers", "kind", "total")
    plls = res.integer("plls", nullable=True, minimum=0)
    pins = res.integer("user_pins", required=False, nullable=True, minimum=0)
    res.done()
    return Resources(logic, block, mult, plls, pins)


def _clocks(top: Section) -> Clocks | None:
    """Read the `clocks` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    Clocks or None
        The clocks; None when the section is invalid.
    """
    clocks = top.section("clocks")
    if clocks is None:
        return None
    inputs: list[ClockInput] = []
    for index, item in enumerate(clocks.items("inputs")):
        entry = Section(f"{clocks.label}.inputs[{index}]", item, top.problems)
        name = entry.text("name")
        signal = entry.text("signal")
        mhz = entry.number("mhz", minimum=0)
        entry.done()
        if name and signal and mhz is not None:
            inputs.append(ClockInput(name, signal, mhz))
    reference = clocks.text("reference")
    reset = clocks.section("reset")
    signal = level = None
    if reset is not None:
        signal = reset.text("signal")
        level = reset.text("active", choices=ACTIVE_LEVELS)
        reset.done()
    clocks.done()
    if reference and reference not in {c.name for c in inputs}:
        clocks.fail("reference", f"names no input ({reference})")
    if reference is None or signal is None or level is None:
        return None
    return Clocks(tuple(inputs), reference, signal, level)


def role_section(io: Section, role: str) -> Section | None:
    """Open the section of an I/O role with the `signals` form.

    Parameters
    ----------
    io : Section
        The `io` section.
    role : str
        The key being read.

    Returns
    -------
    Section or None
        The role section; None for an unknown role (reported) and for
        the video, which has fields of its own.
    """
    if role not in IO_ROLES:
        io.fail(role, f"is not a role ({', '.join(IO_ROLES)})")
        return None
    return None if role == "video" else io.section(role)


def _io_role(entry: Section, role: str) -> IoRole | None:
    """Read one role of the `io` section.

    Parameters
    ----------
    entry : Section
        The section of the role.
    role : str
        The role.

    Returns
    -------
    IoRole or None
        The role; None, after reporting, when it is not valid. `signals`
        is one group or a list of groups (the pins of the role are
        numbered in the order of the list). `active` is required except
        in the roles of general use, which have no polarity.
        `bidirectional: true` (or `direction: inout`) asks the top for
        `inout` ports.
    """
    groups = entry.one_or_more("signals")
    general = role in GENERAL_ROLES
    active = entry.text("active", required=not general, choices=ACTIVE_LEVELS)
    both = entry.flag("bidirectional", required=False)
    direction = entry.text("direction", required=False, choices=("inout",))
    entry.done()
    if not groups or not (active or general):
        return None
    return IoRole(
        groups[0],
        active or "high",
        groups if len(groups) > 1 else (),
        both or direction == "inout",
    )


def _io(top: Section) -> dict[str, IoRole]:
    """Read the `io` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    dict of str to IoRole
        The roles the board has.
    """
    io = top.section("io", required=False)
    roles: dict[str, IoRole] = {}
    if io is None:
        return roles
    for role in io.names():
        entry = role_section(io, role)
        if entry is None:
            continue
        found = _io_role(entry, role)
        if found is not None:
            roles[role] = found
    return roles


def _video(top: Section) -> VideoRole | None:
    """Read the `io.video` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    VideoRole or None
        The video output; None when the board has none or it is invalid.
    """
    io = top.section("io", required=False)
    if io is None or "video" not in io.names():
        return None
    entry = io.section("video")
    return None if entry is None else parse_video_role(entry)


def _memory(key: str, entry: Section) -> MemoryDevice:
    """Read one entry of `memories`.

    Parameters
    ----------
    key : str
        The kind of the memory.
    entry : Section
        The entry.

    Returns
    -------
    MemoryDevice
        The memory.
    """
    if key == "onchip_flash":
        entry.text("kind")
        size = entry.integer("user_bytes", minimum=1)
        return MemoryDevice(bytes=size)
    if key == "serial_flash":
        chip = entry.text("chip", nullable=True)
        size = entry.integer("bytes", minimum=1)
        entry.flag("shared_with_config", required=False)
        return MemoryDevice(chip=chip, bytes=size)
    chip = entry.text("chip")
    signals = entry.one_or_more("signals")
    if key == "sdram":
        chips = entry.integer("chips", minimum=1) or 1
        phase = entry.integer("clk_phase_ps", nullable=True, minimum=0)
        return MemoryDevice(chip, chips, None, signals, phase)
    width = entry.integer("bus_width", minimum=1)
    return MemoryDevice(chip, 1, width, signals)


def _memories(top: Section) -> dict[str, MemoryDevice]:
    """Read the `memories` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    dict of str to MemoryDevice
        The memories the board carries.
    """
    section = top.section("memories", required=False)
    found: dict[str, MemoryDevice] = {}
    if section is None:
        return found
    for key in section.names():
        if key not in MEMORY_KEYS:
            section.fail(key, f"is not a memory ({', '.join(MEMORY_KEYS)})")
            continue
        entry = section.section(key)
        if entry is not None:
            found[key] = _memory(key, entry)
            entry.done()
    return found


def _console(top: Section) -> Console:
    """Read the `console` section.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    Console
        The default console and the UART, empty without one.
    """
    console = top.section("console", required=False)
    if console is None:
        return Console("jtag", ())
    default = console.text("default", required=False, choices=("jtag",))
    uart = console.section("uart", required=False)
    console.done()
    signals: tuple[str, ...] = ()
    if uart is not None:
        rx = uart.text("rx")
        tx = uart.text("tx")
        uart.done()
        signals = (rx, tx) if rx and tx else ()
    return Console(default or "jtag", signals)


def parse_board(raw: Any, label: str = "board") -> Board:
    """Read a board file, checking every field.

    Parameters
    ----------
    raw : Any
        The parsed YAML.
    label : str, optional
        The name used in the messages.

    Returns
    -------
    Board
        The board.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section(label, raw, problems)
    # A ordem do literal é a ordem em que o arquivo é lido e relatado.
    values: dict[str, Any] = {
        "board": top.text("board"),
        "name": top.text("name"),
        "family": top.text("family"),
        "device": top.text("device"),
        "speed_grade": top.text("speed_grade"),
        "target_level": top.text(
            "target_level", required=False, choices=LEVELS
        ),
        "jtag": _jtag(top),
        "resources": _resources(top),
        "clocks": _clocks(top),
        "io": _io(top),
        "memories": _memories(top),
        "console": _console(top),
        "pins": top.text("pins"),
        "notes": tuple(top.texts("notes", required=False)),
        "video": _video(top),
    }
    top.done()
    raise_if(problems)
    return Board(**values)
