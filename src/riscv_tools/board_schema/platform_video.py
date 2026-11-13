"""Read the `io.video` request of a `platform.yaml`."""

from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.board_schema.fields import Section, raise_if
from riscv_tools.board_schema.video import CHANNEL_BITS, read_aspect

# Nome do periférico de vídeo na lista `peripherals` da plataforma.
VIDEO_PERIPHERAL = "VIDEO"


@dataclass(frozen=True)
class PlatformVideo:
    """What the platform asks of the video output.

    Every field is optional, and a request with no field takes the
    default mode of the board.

    Parameters
    ----------
    width : int or None
        The visible columns of the mode.
    height : int or None
        The visible lines of the mode.
    aspect : str or None
        `4:3` or `16:9`.
    refresh_hz : int or None
        The refresh rate, to tell two modes of one size apart.
    channel_bits : int or None
        The bits of each color channel; the board value when None.
    fb_width : int or None
        The columns of the framebuffer; the visible columns when None.
    fb_height : int or None
        The lines of the framebuffer; the visible lines when None.
    outside_manual : bool
        Whether a mode that the manual of the board does not list may be
        used.
    """

    width: int | None = None
    height: int | None = None
    aspect: str | None = None
    refresh_hz: int | None = None
    channel_bits: int | None = None
    fb_width: int | None = None
    fb_height: int | None = None
    outside_manual: bool = False


def _requested(platform: dict[str, Any]) -> bool:
    """Tell whether a platform lists the video peripheral.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    bool
        True when `peripherals` has an entry named `VIDEO`.
    """
    items = platform.get("peripherals")
    if not isinstance(items, list):
        return False
    return any(
        isinstance(item, dict)
        and cast("dict[str, Any]", item).get("name") == VIDEO_PERIPHERAL
        for item in cast("list[Any]", items)
    )


def _read(entry: Section) -> PlatformVideo:
    """Read the fields of an `io.video` section.

    Parameters
    ----------
    entry : Section
        The section.

    Returns
    -------
    PlatformVideo
        The request.
    """
    width = entry.integer("width", required=False, minimum=1)
    height = entry.integer("height", required=False, minimum=1)
    aspect = read_aspect(entry, "aspect")
    refresh = entry.integer("refresh_hz", required=False, minimum=1)
    bits = entry.integer("channel_bits", required=False)
    fb_width = entry.integer("fb_width", required=False, minimum=1)
    fb_height = entry.integer("fb_height", required=False, minimum=1)
    outside = entry.flag("outside_manual", required=False)
    entry.done()
    if bits is not None and bits not in CHANNEL_BITS:
        entry.fail("channel_bits", "must be 4 or 8")
        bits = None
    if (width is None) != (height is None):
        entry.fail("width", "and height must be written together")
    if (fb_width is None) != (fb_height is None):
        entry.fail("fb_width", "and fb_height must be written together")
    return PlatformVideo(
        width, height, aspect, refresh, bits, fb_width, fb_height, outside
    )


def parse_platform_video(
    platform: dict[str, Any], section: Section | None, problems: list[str]
) -> PlatformVideo | None:
    """Read the video request of a platform.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    section : Section or None
        The `io` section, None when the platform has none.
    problems : list of str
        Receives the problems found.

    Returns
    -------
    PlatformVideo or None
        The request. A platform that writes `io.video` (even empty) or
        lists the `VIDEO` peripheral asks for video; None means it asks
        for none.
    """
    if section is None or "video" not in section.names():
        return PlatformVideo() if _requested(platform) else None
    entry = section.section("video", nullable=True)
    if entry is None:
        return PlatformVideo()
    count = len(problems)
    request = _read(entry)
    return request if len(problems) == count else PlatformVideo()


def read_platform_video(platform: dict[str, Any]) -> PlatformVideo | None:
    """Read only the video request of a platform.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    PlatformVideo or None
        The request; None when the platform asks for no video.

    Raises
    ------
    SchemaError
        If a field of the request is misspelled or of the wrong type.
    """
    problems: list[str] = []
    top = Section("platform", platform, problems)
    request = parse_platform_video(
        platform, top.section("io", required=False), problems
    )
    raise_if(problems)
    return request
