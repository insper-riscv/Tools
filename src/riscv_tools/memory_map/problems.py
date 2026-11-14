"""Gather every consistency problem of a platform's own sections."""

from typing import Any

from riscv_tools.memory_map import (
    banks,
    core_checks,
    interrupts,
    sdram_clock,
)
from riscv_tools.memory_map.core import Mismatch
from riscv_tools.memory_map.validation import validate_platform


def platform_problems(
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None = None,
    xlen: int | None = None,
) -> list[Mismatch]:
    """Check the map, the banks, the interrupts and the clocks.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}, optional
        The generics of the profile; without them the checks that need
        the profile (Zifencei under a cache, the interrupts, V-A5) are
        skipped.
    xlen : int, optional
        The register width of V-A2 and V-A5, in place of the one of the
        profile of the platform.

    Returns
    -------
    list of Mismatch
        The problems; empty when the platform is consistent.
    """
    return (
        validate_platform(platform, generics, xlen)
        + core_checks.problems(platform, xlen)
        + banks.problems(platform)
        + interrupts.problems(platform, generics)
        + sdram_clock.problems(platform)
    )
