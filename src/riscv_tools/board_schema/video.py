"""Read the video of a board and the catalog of video modes.

The board states what its output offers (`io.video` of the
`board.yaml`), and the timing of each mode lives once in the catalog
`boards/video-modes.yaml`, so two boards that accept `640x480@60` read
the same totals, synchronisms and polarities.
"""

import re
from typing import Any

from riscv_tools.board_schema.fields import Section, raise_if
from riscv_tools.board_schema.model import VideoAxis, VideoMode, VideoRole

VIDEO_KINDS = ("vga", "hdmi")
CHANNEL_BITS = (4, 8)
POLARITIES = ("negative", "positive")
ASPECTS = ("4:3", "16:9")
MODE_NAME = re.compile(r"^(\d+)x(\d+)@(\d+)$")
# O YAML 1.1 lê `4:3` e `16:9` sem aspas como números sexagesimais.
_SEXAGESIMAL = {4 * 60 + 3: "4:3", 16 * 60 + 9: "16:9"}


def read_aspect(entry: Section, key: str) -> str | None:
    """Read a proportion, taking the form YAML turns into a number.

    Parameters
    ----------
    entry : Section
        The section that holds the field.
    key : str
        The field.

    Returns
    -------
    str or None
        `4:3` or `16:9`; None when the field is absent or invalid.
    """
    value = entry.get(key)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        value = _SEXAGESIMAL.get(value, value)
    if value not in ASPECTS:
        entry.fail(key, f"must be one of {', '.join(ASPECTS)}")
        return None
    return str(value)


def parse_video_role(entry: Section) -> VideoRole | None:
    """Read the `io.video` section of a board.

    Parameters
    ----------
    entry : Section
        The `io.video` section.

    Returns
    -------
    VideoRole or None
        The role; None when a field is invalid.
    """
    kind = entry.text("kind", choices=VIDEO_KINDS)
    bits = entry.integer("channel_bits")
    signals = entry.text("signals")
    default = entry.text("default_mode")
    modes = tuple(entry.texts("modes"))
    entry.done()
    if bits is not None and bits not in CHANNEL_BITS:
        entry.fail("channel_bits", "must be 4 or 8")
        bits = None
    for name in modes:
        if not MODE_NAME.match(name):
            entry.fail("modes", f"{name!r} is not <width>x<height>@<hertz>")
    if default is not None and default not in modes:
        entry.fail("default_mode", f"{default} is not in modes")
    if None in (kind, bits, signals, default) or not modes:
        return None
    return VideoRole(
        str(kind), int(bits or 0), str(signals), str(default), modes
    )


def _axis(parent: Section, key: str) -> VideoAxis | None:
    """Read the timing of one axis of a mode.

    Parameters
    ----------
    parent : Section
        The mode.
    key : str
        `horizontal` or `vertical`.

    Returns
    -------
    VideoAxis or None
        The axis; None when it is invalid.
    """
    entry = parent.section(key)
    if entry is None:
        return None
    visible = entry.integer("visible", minimum=1)
    front = entry.integer("front_porch", minimum=0)
    sync = entry.integer("sync", minimum=1)
    back = entry.integer("back_porch", minimum=0)
    total = entry.integer("total", minimum=1)
    polarity = entry.text("polarity", choices=POLARITIES)
    entry.done()
    values = (visible, front, sync, back, total)
    if None in values or polarity is None:
        return None
    vis, fp, sy, bp, tot = (int(v or 0) for v in values)
    if vis + fp + sy + bp != tot:
        entry.fail(
            "total",
            f"is {tot} but visible + front_porch + sync + back_porch "
            f"is {vis + fp + sy + bp}",
        )
        return None
    return VideoAxis(vis, fp, sy, bp, tot, polarity == "positive")


def _mode(name: str, entry: Section) -> VideoMode | None:
    """Read one mode of the catalog.

    Parameters
    ----------
    name : str
        The name of the mode.
    entry : Section
        Its section.

    Returns
    -------
    VideoMode or None
        The mode; None when it is invalid.
    """
    clock = entry.number("pixel_clock_mhz", minimum=0)
    horizontal = _axis(entry, "horizontal")
    vertical = _axis(entry, "vertical")
    entry.text("source", required=False)
    entry.done()
    found = MODE_NAME.match(name)
    if found is None:
        entry.problems.append(
            f"{entry.label}: the name must be <width>x<height>@<hertz>"
        )
        return None
    if clock is None or horizontal is None or vertical is None:
        return None
    size = (int(found.group(1)), int(found.group(2)))
    if size != (horizontal.visible, vertical.visible):
        entry.problems.append(
            f"{entry.label}: the name says {size[0]}x{size[1]} but "
            f"the visible area is {horizontal.visible}x{vertical.visible}"
        )
        return None
    return VideoMode(name, clock, horizontal, vertical)


def parse_video_modes(
    raw: Any, label: str = "video-modes"
) -> dict[str, VideoMode]:
    """Read the catalog of video modes.

    Parameters
    ----------
    raw : Any
        The parsed YAML.
    label : str, optional
        The name used in the messages.

    Returns
    -------
    dict of str to VideoMode
        The modes by name, in file order.

    Raises
    ------
    SchemaError
        If a field is missing, misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section(label, raw, problems)
    section = top.section("modes")
    found: dict[str, VideoMode] = {}
    if section is not None:
        for name in section.names():
            entry = section.section(name)
            mode = None if entry is None else _mode(name, entry)
            if mode is not None:
                found[name] = mode
    top.done()
    raise_if(problems)
    return found
