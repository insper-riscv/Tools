"""The pixel clock the generated top asks the PLL for."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from riscv_tools.board_video.plan import VideoPlan
from riscv_tools.board_video.resolve import VideoError
from riscv_tools.memory_map.external import external_list
from riscv_tools.memory_map.kinds import (
    EXTERNAL,
    PIXEL_ENTITIES,
    SERIAL_ENTITIES,
)

_KHZ_PER_MHZ = 1000


@dataclass(frozen=True)
class PixelRequest:
    """The video clocks the peripherals of a platform need.

    Parameters
    ----------
    mhz : Fraction
        The pixel clock.
    serial : bool
        Whether a peripheral also takes the serial clock, five times
        the pixel clock.
    """

    mhz: Fraction
    serial: bool = False


def _entities(platform: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """List the entities of the platform, with their entries.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    list of tuple
        The entity and the entry of each external peripheral.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for item in external_list(platform):
        variant = EXTERNAL[str(item["kind"])].variant(item)
        if variant is not None:
            out.append((variant.entity, item))
    return out


def uses_pixel(platform: dict[str, Any]) -> bool:
    """Tell whether a peripheral of the platform takes a pixel clock.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    bool
        True when an external peripheral has the pixel clock port.
    """
    return any(e in PIXEL_ENTITIES for e, _ in _entities(platform))


def _written_khz(users: list[dict[str, Any]]) -> int | None:
    """Read the `pixel_clock_khz` the peripherals write.

    Parameters
    ----------
    users : list of dict of str to Any
        The peripherals that take a pixel clock.

    Returns
    -------
    int or None
        The written value, or None when no peripheral writes one.

    Raises
    ------
    VideoError
        If two peripherals write different values.
    """
    written = {
        int(i["pixel_clock_khz"]) for i in users if "pixel_clock_khz" in i
    }
    if len(written) > 1:
        raise VideoError(
            "peripherals write different pixel_clock_khz values "
            f"({', '.join(str(v) for v in sorted(written))})"
        )
    return next(iter(written), None)


def pixel_request(
    platform: dict[str, Any], video: VideoPlan | None
) -> PixelRequest | None:
    """Tell which video clocks the peripherals of a platform take.

    The pixel clock is the one of the resolved mode; a peripheral that
    writes `pixel_clock_khz` asks for the same value, and the two must
    agree. Without a resolved mode the written value is the only source.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    video : VideoPlan or None
        The resolved video.

    Returns
    -------
    PixelRequest or None
        None when no peripheral takes a pixel clock, or when no source
        gives its frequency.

    Raises
    ------
    VideoError
        If a `pixel_clock_khz` differs from the clock of the mode, or
        two peripherals write different values.
    """
    users = [
        item
        for entity, item in _entities(platform)
        if entity in PIXEL_ENTITIES
    ]
    if not users:
        return None
    serial = any(e in SERIAL_ENTITIES for e, _ in _entities(platform))
    written = _written_khz(users)
    mode = Fraction(str(video.mode.pixel_clock_mhz)) if video else None
    if written is not None:
        khz = Fraction(written, _KHZ_PER_MHZ)
        if mode is not None and khz != mode:
            raise VideoError(
                f"pixel_clock_khz {written} differs from the "
                f"{mode} MHz of mode {video.mode.name if video else ''}"
            )
        mode = khz
    return None if mode is None else PixelRequest(mode, serial)
