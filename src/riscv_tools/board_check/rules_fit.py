"""The rule of the fit: V11 to V13 and the V18 of a missing coefficient.

The rule reads the platform and the board and runs the estimator of
`fit_estimate` (section 7 of the plan), which is the one place that
knows the cost of a block. The same function feeds `capacity.json` of
`board generate`.
"""

from typing import Any, cast

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import Finding
from riscv_tools.board_schema import Board
from riscv_tools.calibration.profiles import (
    DEFAULT_HPM_COUNTERS,
    DEFAULT_HPM_WIDTH,
    parse_profile_name,
)
from riscv_tools.fit_estimate import (
    Capacity,
    Estimate,
    ProfileSpec,
    estimate,
)
from riscv_tools.fit_estimate.table import CalibrationTable
from riscv_tools.memory_map.core import platform_list
from riscv_tools.memory_map.expressions import evaluate

BITS_PER_KBIT = 1024
# Peripherals of the platform that the calibration table separates.
TABLE_PERIPHERALS = {
    "CLINT": "CLINT",
    "PLIC": "PLIC_base",
    "UART": "UART",
    "DISPLAY": "DISPLAY",
    "FLASH_CTRL": "FLASH_CTRL",
}
# Widths (bits) of the data bus that have a controller in the table.
SDRAM_WIDTHS = (16, 32)


def _power_of_two(value: int) -> int:
    """Round a byte count up to the size an address width stores.

    Parameters
    ----------
    value : int
        The bytes.

    Returns
    -------
    int
        The least power of two that is not below `value`.
    """
    return 1 << max(0, (value - 1).bit_length())


def _cache_kbit(platform: dict[str, Any], key: str) -> float | None:
    """Read the size of a cache of the platform.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    key : str
        `icache` or `dcache`.

    Returns
    -------
    float or None
        The size in kbit; None when the cache is off or absent.
    """
    memory = cast(dict[str, Any], platform.get("memory") or {})
    entry = cast(dict[str, Any], memory.get(key) or {})
    if not entry.get("enabled"):
        return None
    return float(evaluate(entry["size_bits"])) / BITS_PER_KBIT


def _emulated_bytes(platform: dict[str, Any]) -> tuple[int, ...]:
    """List the memories the FPGA holds in blocks of RAM.

    The boot memory is always inside the core, and an emulated region
    stores a whole power of two of bytes because the address width, and
    not the size, decides the blocks.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    tuple of int
        The bytes of each memory.
    """
    regions = platform_list(platform, "regions")
    memory = cast(dict[str, Any], platform.get("memory") or {})
    sizes = [evaluate(regions[0]["size"])] if regions else []
    for region in regions[1:]:
        kind = "ram" if region.get("kind") == "ram" else "rom"
        entry = cast(dict[str, Any], memory.get(kind) or {})
        if not entry.get("external") or entry.get("backend") == "emulado":
            sizes.append(_power_of_two(evaluate(region["size"])))
    return tuple(sizes)


def _backends(ctx: Context) -> tuple[str, ...]:
    """Name the controllers of device the platform uses.

    Parameters
    ----------
    ctx : Context
        The platform against one board, for the width of the SDRAM.

    Returns
    -------
    tuple of str
        `sdram_16`, `sdram_32`, `nor` or `sram`, without repeats.
    """
    found: list[str] = []
    for use in ctx.used_devices().values():
        if use.device == "sdram":
            chip = ctx.chip_of("sdram")
            memory = ctx.board.memories["sdram"]
            width = (
                int(chip.organization["width"]) * memory.chips if chip else 0
            )
            if width in SDRAM_WIDTHS:
                found.append(f"sdram_{width}")
        elif use.device in ("nor", "sram"):
            found.append(str(use.device))
    return tuple(dict.fromkeys(found))


def profile_spec(ctx: Context) -> ProfileSpec:
    """Read the profile of a platform as the estimator sees it.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    ProfileSpec
        Base, extensions, extras, Zihpm size, caches, peripherals,
        backends and emulated memories.
    """
    platform = ctx.platform
    base, extensions = parse_profile_name(str(platform["profile"]))
    names = {
        str(item["name"]) for item in platform_list(platform, "peripherals")
    }
    return ProfileSpec(
        base=base,
        extensions=extensions,
        extras=frozenset(str(x) for x in platform.get("extras") or ()),
        hpm_counters=DEFAULT_HPM_COUNTERS,
        hpm_width=DEFAULT_HPM_WIDTH,
        icache_kbit=_cache_kbit(platform, "icache"),
        dcache_kbit=_cache_kbit(platform, "dcache"),
        peripherals=frozenset(
            term for name, term in TABLE_PERIPHERALS.items() if name in names
        ),
        backends=_backends(ctx),
        emulated_bytes=_emulated_bytes(platform),
    )


def capacity_of(board: Board) -> Capacity | None:
    """Read the capacities of a board for the estimator.

    Parameters
    ----------
    board : Board
        The board.

    Returns
    -------
    Capacity or None
        The capacities; None when the board lacks one of them.
    """
    res = board.resources
    bits = res.block_ram.bits_per_block
    totals = (
        res.logic.total,
        res.block_ram.total,
        res.multipliers.total,
        res.plls,
        bits,
    )
    if any(value is None for value in totals):
        return None
    return Capacity(
        logic_unit=res.logic.kind,
        logic=cast(int, res.logic.total),
        ram_blocks=cast(int, res.block_ram.total),
        bits_per_block=cast(int, bits),
        multipliers=cast(int, res.multipliers.total),
        plls=cast(int, res.plls),
        user_pins=res.user_pins,
    )


def estimate_context(ctx: Context) -> tuple[Estimate, Capacity] | None:
    """Estimate the fit of the platform on the board of the context.

    Parameters
    ----------
    ctx : Context
        The platform against one board and the table of its family.

    Returns
    -------
    tuple of (Estimate, Capacity) or None
        The estimate and the capacities; None when the family has no
        table or the board lacks a capacity (V18 says so).
    """
    capacity = capacity_of(ctx.board)
    table: CalibrationTable | None = ctx.table
    if table is None or capacity is None or "profile" not in ctx.platform:
        return None
    return (
        estimate(profile_spec(ctx), table, capacity, ctx.board.board),
        capacity,
    )


def rule_fit(ctx: Context) -> list[Finding]:
    """Check that the profile fits the board (V11 to V13).

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The errors above 100 % of a resource, the warnings above 85 %
        and the V18 of a coefficient the table lacks.
    """
    result = estimate_context(ctx)
    if result is None:
        return []
    return [
        Finding(item.code, item.severity, item.message[2:])
        for item in result[0].findings
    ]


def capacity_report(ctx: Context) -> dict[str, Any] | None:
    """Write the estimate as the report of `board generate`.

    Parameters
    ----------
    ctx : Context
        The platform against one board and the table of its family.

    Returns
    -------
    dict of str to Any or None
        The board, the unit, the numbers of each resource and the
        findings; None when there is nothing to estimate.
    """
    result = estimate_context(ctx)
    if result is None:
        return None
    outcome, capacity = result
    logic = None if outcome.logic is None else round(outcome.logic)
    return {
        "board": ctx.board.board,
        "family": ctx.family.family,
        "unit": capacity.logic_unit,
        "logic": {
            "estimated": logic,
            "total": capacity.logic,
            "utilization": (
                None if logic is None else round(logic / capacity.logic, 4)
            ),
        },
        "ram_blocks": {
            "estimated": outcome.blocks,
            "total": capacity.ram_blocks,
            "utilization": round(outcome.blocks / capacity.ram_blocks, 4),
        },
        "missing": list(outcome.missing),
        "findings": [item.message for item in outcome.findings],
    }
