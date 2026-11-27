"""Tests for the fetch clock that is the core clock."""

from fractions import Fraction

from support import check_equal

from riscv_tools.board_clocks import ClockPlan, ClockRole
from riscv_tools.top_generator.generics import fetch_aligned


def _plan(*roles: ClockRole) -> ClockPlan:
    """Return a plan with the given clocks."""
    return ClockPlan("CLOCK_50", Fraction(50), roles)


def test_a_fetch_clock_equal_to_the_core_is_aligned() -> None:
    """Same frequency and phase: the memories read the next address."""
    plan = _plan(
        ClockRole("core", Fraction(100), 0),
        ClockRole("fetch", Fraction(100), 0),
    )
    check_equal(fetch_aligned(plan), True)


def test_a_staggered_or_missing_fetch_clock_is_not_aligned() -> None:
    """A phase or frequency apart, or no fetch clock, is not aligned."""
    core = ClockRole("core", Fraction(100), 3125)
    check_equal(
        fetch_aligned(_plan(core, ClockRole("fetch", Fraction(100), 0))), False
    )
    check_equal(
        fetch_aligned(_plan(core, ClockRole("fetch", Fraction(50), 3125))),
        False,
    )
    check_equal(fetch_aligned(_plan(core)), False)
