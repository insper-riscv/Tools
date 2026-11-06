"""Tests for pll_generator."""

from fractions import Fraction

import pytest
from multifpga_support import inputs_of
from support import check, check_equal, check_in

from riscv_tools.board_clocks import ClockRole, clock_plan
from riscv_tools.pll_generator import (
    PllError,
    PllIpPendingError,
    generate_pll,
    register_renderer,
    renderer_for,
    solve,
)
from riscv_tools.pll_generator import core as pll_core

CYCLONE_V = {"ip": "altera_pll", "vco_mhz": [600, 1600], "outputs_max": 5}


def _de0_cv() -> tuple[Fraction, tuple[ClockRole, ...]]:
    """Return the reference and clocks of the DE0-CV fixture."""
    plan = clock_plan(inputs_of("de0-cv"))
    return plan.reference_mhz, plan.roles


def test_the_de0_cv_clocks_solve_to_the_1000_mhz_vco() -> None:
    """The lowest VCO with exact phase steps is today's 1000 MHz."""
    reference, roles = _de0_cv()
    solution = solve(reference, roles, CYCLONE_V)
    check_equal(solution.vco_mhz, 1000)
    check_equal((solution.n, solution.m), (1, 20))
    check_equal([o.divider for o in solution.outputs], [10, 10, 20, 20])


def test_the_text_has_the_parameters_of_the_handwritten_pll() -> None:
    """Frequencies, phases and output order of sdram_platform_pll.v."""
    reference, roles = _de0_cv()
    rendered, _ = generate_pll("pll_x", reference, roles, CYCLONE_V)
    text = rendered.text
    for fragment in (
        '.reference_clock_frequency("50.000000 MHz")',
        '.output_clock_frequency0("100.000000 MHz")',
        '.phase_shift1("4000 ps")',
        '.output_clock_frequency2("50.000000 MHz")',
        '.phase_shift3("8250 ps")',
        ".number_of_clocks(4)",
        "module pll_x (",
    ):
        check_in(fragment, text)
    check_equal(len(rendered.qsf_lines), 3)
    check_in("*pll_x*", rendered.qsf_lines[0])


def test_a_phase_off_the_vco_step_is_refused() -> None:
    """V7: no VCO makes 8301 ps an exact step."""
    reference, roles = _de0_cv()
    bad = (*roles[:3], ClockRole("core", roles[3].mhz, 8301))
    with pytest.raises(PllError, match="no VCO"):
        solve(reference, bad, CYCLONE_V)


def test_a_frequency_without_an_integer_divider_is_refused() -> None:
    """A 1 MHz clock needs a divider above 511 at any VCO."""
    reference, _ = _de0_cv()
    with pytest.raises(PllError, match="integer dividers"):
        solve(reference, (ClockRole("core", Fraction(1), 0),), CYCLONE_V)


def test_more_outputs_than_the_family_gives_are_refused() -> None:
    """V15: the family limit on outputs."""
    reference, roles = _de0_cv()
    with pytest.raises(PllError, match="needs 4 PLL outputs"):
        solve(reference, roles, CYCLONE_V | {"outputs_max": 3})


def test_altpll_is_the_extension_point() -> None:
    """Without a renderer altpll fails clearly; with one it works."""
    reference, roles = _de0_cv()
    altpll = {"ip": "altpll", "vco_mhz": [600, 1300], "outputs_max": 5}
    with pytest.raises(PllIpPendingError, match=r"M\.0\.2"):
        generate_pll("p", reference, roles, altpll)
    calls: list[str] = []

    def fake(
        module: str, _solution: pll_core.PllSolution
    ) -> pll_core.RenderedPll:
        calls.append(module)
        return pll_core.RenderedPll(module, ".v", "fake", ())

    register_renderer("altpll", fake)
    try:
        rendered, _ = generate_pll("p", reference, roles, altpll)
        check_equal(rendered.text, "fake")
        check_equal(calls, ["p"])
        check(renderer_for("altpll") is fake)
    finally:
        del pll_core.RENDERERS["altpll"]
