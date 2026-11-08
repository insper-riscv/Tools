"""The rules about the clocks: V7, V8 and V15."""

import math

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import (
    Finding,
    error,
    mhz_text,
    warning,
)


def rule_v7(ctx: Context) -> list[Finding]:
    """Report a clock beyond what the PLL or the chip can do.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The errors.
    """
    found: list[Finding] = []
    ceiling = ctx.family.pll.vco_mhz[1]
    for name, clock in ctx.fields.clocks.items():
        if clock.mhz > ceiling:
            found.append(
                error(
                    "V7",
                    f"clocks.{name} {mhz_text(clock.mhz)} MHz exceeds the "
                    f"PLL range of family '{ctx.family.family}' "
                    f"({mhz_text(ceiling)} MHz)",
                )
            )
    mem = ctx.fields.clocks.get("mem")
    for use in ctx.used_devices().values():
        chip = ctx.chip_of(str(use.device))
        limit = None if chip is None else chip.max_mhz
        if (
            mem is not None
            and chip is not None
            and limit is not None
            and mem.mhz > limit
        ):
            found.append(
                error(
                    "V7",
                    f"clocks.mem {mhz_text(mem.mhz)} MHz exceeds chip "
                    f"{chip.chip} limit ({mhz_text(limit)} MHz)",
                )
            )
    return found


def rule_v8(ctx: Context) -> list[Finding]:
    """Warn of a core clock above the measured Fmax of the family.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The warning, when there is a measured value to compare with.
    """
    core = ctx.fields.clocks.get("core")
    measured = ctx.family.fmax_by_grade.get(ctx.board.speed_grade)
    if core is None or measured is None or core.mhz <= measured:
        return []
    return [
        warning(
            "V8",
            f"clocks.core {mhz_text(core.mhz)} MHz exceeds the measured "
            f"Fmax (about {mhz_text(measured)} MHz, family "
            f"{ctx.family.family}, grade {ctx.board.speed_grade})",
        )
    ]


def pll_outputs(ctx: Context) -> int:
    """Count the PLL outputs the platform needs.

    Each distinct pair of frequency and phase among the clocks is one
    output, and an SDRAM adds the output of the clock that leaves for
    the chip.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    int
        The outputs.
    """
    outputs = {(c.mhz, c.phase_ps) for c in ctx.fields.clocks.values()}
    mem = ctx.fields.clocks.get("mem")
    sdram = ctx.board.memories.get("sdram")
    uses_sdram = any(
        use.device == "sdram" for use in ctx.used_devices().values()
    )
    if mem is not None and sdram is not None and uses_sdram:
        outputs.add((mem.mhz, sdram.clk_phase_ps or 0))
    return len(outputs)


def rule_v15(ctx: Context) -> list[Finding]:
    """Report more clocks than the PLLs of the board can make.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The error, when the board has the count of PLLs and it is short.
    """
    provided = ctx.board.resources.plls
    outputs = pll_outputs(ctx)
    needed = math.ceil(outputs / ctx.family.pll.outputs_max)
    if provided is None or needed <= provided:
        return []
    return [
        error(
            "V15",
            f"platform needs {outputs} PLL outputs on {needed} PLLs; "
            f"board '{ctx.board.board}' provides {provided}",
        )
    ]
