"""The rules about the video output: V20, V21 and V22."""

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import Finding, error, warning
from riscv_tools.board_check.rules_fit import capacity_of, estimate_context
from riscv_tools.board_clocks import clock_plan
from riscv_tools.board_inputs import (
    BoardInputs,
    InputError,
    board_view,
    chip_view,
    family_view,
)
from riscv_tools.board_video import (
    VideoError,
    VideoPlan,
    framebuffer_problem,
    pixel_clock_problem,
    plan_video,
)


def _pixel_clock(ctx: Context, plan: VideoPlan) -> list[Finding]:
    """Check that the PLL of the board can make the pixel clock.

    Parameters
    ----------
    ctx : Context
        The platform against one board.
    plan : VideoPlan
        The resolved video.

    Returns
    -------
    list of Finding
        The V21 error; empty when the PLL can make it, or when the
        clocks of the platform are invalid (the clock rules say so).
    """
    inputs = BoardInputs(
        ctx.platform,
        board_view(ctx.board),
        {},
        family_view(ctx.family),
        {name: chip_view(chip) for name, chip in ctx.chips.items()},
    )
    try:
        clocks = clock_plan(inputs)
    except InputError:
        return []
    problem = pixel_clock_problem(
        plan,
        clocks.reference_mhz,
        clocks.roles,
        family_view(ctx.family)["pll"],
    )
    return [] if problem is None else [error("V21", problem)]


def _framebuffer(ctx: Context, plan: VideoPlan) -> list[Finding]:
    """Check that the framebuffer fits the free memory blocks.

    Parameters
    ----------
    ctx : Context
        The platform against one board.
    plan : VideoPlan
        The resolved video.

    Returns
    -------
    list of Finding
        The V22 error; empty when it fits or when the board lacks the
        capacity to compare with.
    """
    result = estimate_context(ctx)
    if result is not None:
        outcome, capacity = result
        used = outcome.blocks
    else:
        # Sem tabela de calibração só se sabe o total do dispositivo.
        found = capacity_of(ctx.board)
        if found is None:
            return []
        capacity, used = found, 0
    problem = framebuffer_problem(
        plan,
        capacity.ram_blocks - used,
        capacity.ram_blocks,
        capacity.bits_per_block,
    )
    return [] if problem is None else [error("V22", problem)]


def rule_video(ctx: Context) -> list[Finding]:
    """Check the video the platform asks for against the board.

    Parameters
    ----------
    ctx : Context
        The platform against one board and the catalog of modes.

    Returns
    -------
    list of Finding
        V20 for a mode that does not exist, a proportion that does not
        match the size, a mode outside the manual or more bits than the
        board wires; V21 for a pixel clock the PLL cannot make; V22 for
        a framebuffer that does not fit. Empty when the platform asks
        for no video.
    """
    request = ctx.fields.video
    if request is None:
        return []
    role = ctx.board.video
    if role is None:
        return [
            error(
                "V20",
                f"io.video asked but board '{ctx.board.board}' has no "
                f"io.video",
            )
        ]
    try:
        plan = plan_video(role, ctx.video_modes, request)
    except VideoError as bad:
        return [error("V20", str(bad))]
    found = [warning("V20", text[2:]) for text in plan.warnings]
    return found + _pixel_clock(ctx, plan) + _framebuffer(ctx, plan)
