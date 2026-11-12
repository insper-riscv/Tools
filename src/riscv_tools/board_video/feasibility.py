"""Whether the board can run a resolved video (PLL and memory)."""

from fractions import Fraction
from typing import Any

from riscv_tools.board_clocks import ClockRole
from riscv_tools.board_video.plan import VideoPlan
from riscv_tools.pll_generator import PllError, solve

VIDEO_ROLE = "video"


def pixel_clock_problem(
    plan: VideoPlan,
    reference_mhz: Fraction,
    others: tuple[ClockRole, ...],
    pll: dict[str, Any],
) -> str | None:
    """Tell whether the PLL can make the pixel clock.

    The pixel clock is one more output of the PLL that already makes the
    clocks of the platform, so it has to share their oscillator.

    Parameters
    ----------
    plan : VideoPlan
        The resolved video.
    reference_mhz : Fraction
        The frequency that feeds the PLL.
    others : tuple of ClockRole
        The clocks the platform already asks the PLL for.
    pll : dict of str to Any
        The `pll` section of the family.

    Returns
    -------
    str or None
        The message; None when the PLL can make all the clocks.
    """
    clock = ClockRole(VIDEO_ROLE, Fraction(str(plan.mode.pixel_clock_mhz)), 0)
    try:
        solve(reference_mhz, (*others, clock), pll)
    except PllError as bad:
        alone = _alone(clock, reference_mhz, pll)
        return (
            f"pixel clock {plan.mode.pixel_clock_mhz} MHz of mode "
            f"{plan.mode.name} cannot be made by the PLL"
            f"{alone}: {str(bad).removeprefix('E ')}"
        )
    return None


def _alone(
    clock: ClockRole, reference_mhz: Fraction, pll: dict[str, Any]
) -> str:
    """Say whether the pixel clock alone is within reach of the PLL.

    Parameters
    ----------
    clock : ClockRole
        The pixel clock.
    reference_mhz : Fraction
        The frequency that feeds the PLL.
    pll : dict of str to Any
        The `pll` section of the family.

    Returns
    -------
    str
        A phrase that tells the cause apart: the clock itself or the
        other clocks of the platform.
    """
    try:
        solve(reference_mhz, (clock,), pll)
    except PllError:
        return " from this reference"
    return " together with the other clocks of the platform"


def framebuffer_problem(
    plan: VideoPlan, free_blocks: int, total_blocks: int, block_bits: int
) -> str | None:
    """Tell whether the framebuffer fits the free memory blocks.

    Parameters
    ----------
    plan : VideoPlan
        The resolved video.
    free_blocks : int
        The memory blocks the rest of the platform leaves free.
    total_blocks : int
        The memory blocks of the device.
    block_bits : int
        The bits of one memory block.

    Returns
    -------
    str or None
        The message; None when the framebuffer fits.
    """
    needed = -(-plan.framebuffer_bits // block_bits)
    if needed <= free_blocks:
        return None
    return (
        f"framebuffer {plan.fb_width}x{plan.fb_height} at "
        f"{plan.pixel_bits} bits per pixel needs {needed} memory blocks "
        f"but only {max(free_blocks, 0)} of {total_blocks} are free; "
        f"write io.video fb_width and fb_height smaller or a lower "
        f"channel_bits"
    )
