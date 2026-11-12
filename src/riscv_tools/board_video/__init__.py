"""Resolve and check the video output of a platform on a board."""

from riscv_tools.board_video.feasibility import (
    framebuffer_problem,
    pixel_clock_problem,
)
from riscv_tools.board_video.plan import VideoPlan, plan_video
from riscv_tools.board_video.resolve import (
    VideoError,
    aspect_of,
    resolve_mode,
)

__all__ = [
    "VideoError",
    "VideoPlan",
    "aspect_of",
    "framebuffer_problem",
    "pixel_clock_problem",
    "plan_video",
    "resolve_mode",
]
