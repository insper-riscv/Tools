"""Choose the video mode of a platform on a board.

The order is the one of the plan. Without a request the mode is the
`default_mode` of the board. With only a proportion it is the largest
mode of that proportion that the manual of the board lists. With a size
it is the mode of that size in the catalog, preferring the modes the
board lists.
"""

from math import gcd

from riscv_tools.board_schema import PlatformVideo, VideoMode, VideoRole


class VideoError(ValueError):
    """The video request cannot be satisfied by the board."""


def aspect_of(width: int, height: int) -> str:
    """Write the proportion of a size in its lowest terms.

    Parameters
    ----------
    width : int
        The columns.
    height : int
        The lines.

    Returns
    -------
    str
        The proportion, such as `4:3`, `16:9` or `5:4`.
    """
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _same_aspect(mode: VideoMode, aspect: str) -> bool:
    """Tell whether a mode has a proportion.

    Parameters
    ----------
    mode : VideoMode
        The mode.
    aspect : str
        `4:3` or `16:9`.

    Returns
    -------
    bool
        True when the visible area has that proportion.
    """
    return aspect_of(mode.width, mode.height) == aspect


def _lookup(catalog: dict[str, VideoMode], name: str, owner: str) -> VideoMode:
    """Find a mode of the catalog by name.

    Parameters
    ----------
    catalog : dict of str to VideoMode
        The catalog of modes.
    name : str
        The mode.
    owner : str
        Who cites the mode, for the message.

    Returns
    -------
    VideoMode
        The mode.

    Raises
    ------
    VideoError
        If the catalog lacks the mode.
    """
    if name not in catalog:
        known = ", ".join(catalog) or "none, video-modes.yaml is empty"
        raise VideoError(
            f"{owner} names mode {name}, which is not in video-modes.yaml "
            f"(known: {known})"
        )
    return catalog[name]


def _by_size(
    role: VideoRole,
    catalog: dict[str, VideoMode],
    request: PlatformVideo,
) -> VideoMode:
    """Find the mode of a requested size.

    Parameters
    ----------
    role : VideoRole
        The video output of the board.
    catalog : dict of str to VideoMode
        The catalog of modes.
    request : PlatformVideo
        The request, with `width` and `height`.

    Returns
    -------
    VideoMode
        The mode; among several refresh rates, the board default, then
        a mode the board lists, then the lowest rate.

    Raises
    ------
    VideoError
        If the catalog has no mode of that size.
    """
    found = [
        mode
        for mode in catalog.values()
        if (mode.width, mode.height) == (request.width, request.height)
        and request.refresh_hz in (None, mode.refresh_hz)
    ]
    if not found:
        rate = "" if request.refresh_hz is None else f"@{request.refresh_hz}"
        sizes = ", ".join(sorted(catalog)) or "none"
        raise VideoError(
            f"io.video {request.width}x{request.height}{rate} is not in "
            f"video-modes.yaml (known: {sizes})"
        )
    return min(
        found,
        key=lambda m: (
            m.name != role.default_mode,
            m.name not in role.modes,
            m.refresh_hz,
        ),
    )


def _by_aspect(
    role: VideoRole,
    catalog: dict[str, VideoMode],
    request: PlatformVideo,
) -> VideoMode:
    """Find the largest mode of a proportion that the board lists.

    Parameters
    ----------
    role : VideoRole
        The video output of the board.
    catalog : dict of str to VideoMode
        The catalog of modes.
    request : PlatformVideo
        The request, with `aspect`.

    Returns
    -------
    VideoMode
        The mode with most pixels; the lowest refresh rate on a tie.

    Raises
    ------
    VideoError
        If the board lists no mode of that proportion.
    """
    aspect = str(request.aspect)
    listed = [
        _lookup(catalog, name, "io.video.modes of the board")
        for name in role.modes
    ]
    found = [
        mode
        for mode in listed
        if _same_aspect(mode, aspect)
        and request.refresh_hz in (None, mode.refresh_hz)
    ]
    if not found:
        shown = ", ".join(
            f"{m.name} ({aspect_of(m.width, m.height)})" for m in listed
        )
        raise VideoError(
            f"io.video aspect {aspect} has no mode among the modes of the "
            f"board: {shown}"
        )
    return min(found, key=lambda m: (-m.width * m.height, m.refresh_hz))


def resolve_mode(
    role: VideoRole,
    catalog: dict[str, VideoMode],
    request: PlatformVideo,
) -> VideoMode:
    """Choose the mode of a request.

    Parameters
    ----------
    role : VideoRole
        The video output of the board.
    catalog : dict of str to VideoMode
        The catalog of modes.
    request : PlatformVideo
        The request of the platform; empty for the board default.

    Returns
    -------
    VideoMode
        The mode.

    Raises
    ------
    VideoError
        If the mode does not exist, the proportion does not match the
        size, or the request cannot choose a mode.
    """
    sized = request.width is not None and request.height is not None
    if sized:
        mode = _by_size(role, catalog, request)
        if request.aspect and not _same_aspect(mode, request.aspect):
            raise VideoError(
                f"io.video {mode.width}x{mode.height} is "
                f"{aspect_of(mode.width, mode.height)}, not "
                f"{request.aspect}"
            )
        return mode
    if request.aspect:
        return _by_aspect(role, catalog, request)
    if request.refresh_hz is not None:
        raise VideoError(
            "io.video refresh_hz needs width and height or aspect"
        )
    return _lookup(catalog, role.default_mode, "default_mode of the board")
