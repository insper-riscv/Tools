"""Builders of a video catalog, boards and platforms for the tests."""

import copy
from pathlib import Path
from typing import Any

from catalog_support import (
    FAMILY,
    fresh_board,
    fresh_platform,
    pin,
    write,
    write_catalog,
)

MODE_ROWS: dict[str, tuple[float, tuple[int, ...], tuple[int, ...], str]] = {
    "640x480@60": (25, (640, 16, 96, 48, 800), (480, 10, 2, 33, 525), "n"),
    "640x480@85": (36, (640, 56, 56, 80, 832), (480, 1, 3, 25, 509), "n"),
    "800x600@60": (40, (800, 40, 128, 88, 1056), (600, 1, 4, 23, 628), "p"),
    "1024x768@60": (65, (1024, 24, 136, 160, 1344), (768, 3, 6, 29, 806), "n"),
    "1280x720@60": (
        74.25,
        (1280, 110, 40, 220, 1650),
        (720, 5, 5, 20, 750),
        "p",
    ),
    "1280x1024@60": (
        108,
        (1280, 48, 112, 248, 1688),
        (1024, 1, 3, 38, 1066),
        "p",
    ),
}


def _axis(row: tuple[int, ...], polarity: str) -> dict[str, Any]:
    """Write one axis of a mode as the catalog does."""
    visible, front, sync, back, total = row
    return {
        "visible": visible,
        "front_porch": front,
        "sync": sync,
        "back_porch": back,
        "total": total,
        "polarity": "positive" if polarity == "p" else "negative",
    }


def video_modes() -> dict[str, Any]:
    """Make the file `video-modes.yaml` of the tests."""
    modes: dict[str, Any] = {}
    for name, (clock, horizontal, vertical, polarity) in MODE_ROWS.items():
        modes[name] = {
            "pixel_clock_mhz": clock,
            "horizontal": _axis(horizontal, polarity),
            "vertical": _axis(vertical, polarity),
        }
    return {"modes": modes}


def video_board(
    bits: int = 8,
    modes: tuple[str, ...] = ("640x480@60", "800x600@60", "1280x720@60"),
    blocks: int = 1000,
) -> dict[str, Any]:
    """Make a board with a video output and room in the memory."""
    board = fresh_board()
    board["resources"]["block_ram"]["blocks"] = blocks
    board["io"]["video"] = {
        "kind": "vga",
        "channel_bits": bits,
        "signals": "VGA",
        "default_mode": modes[0],
        "modes": list(modes),
    }
    return board


def video_family() -> dict[str, Any]:
    """Make a family whose PLL has the outputs a video platform uses."""
    family = copy.deepcopy(FAMILY)
    family["pll"]["outputs_max"] = 6
    return family


def video_platform(**request: Any) -> dict[str, Any]:
    """Make a platform that asks for video with the fields given."""
    platform = fresh_platform()
    platform["io"]["video"] = dict(request)
    return platform


def write_video_catalog(
    root: Path,
    board: dict[str, Any] | None = None,
    modes: dict[str, Any] | None = None,
) -> None:
    """Lay out a catalog with a video board and the catalog of modes."""
    pins = [pin("CLK", "M9"), pin("RST", "P22"), pin("DRAM_CLK", "A1")]
    pins += [pin(f"LED[{i}]", f"L{i}") for i in range(10)]
    pins += [pin(f"VGA_R[{i}]", f"R{i}") for i in range(4)]
    write_catalog(root, board or video_board(), video_family(), pins)
    write(root / "boards" / "video-modes.yaml", modes or video_modes())
