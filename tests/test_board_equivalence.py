"""Tests for board_equivalence (generated DE0-CV against the real)."""

from multifpga_support import FIXTURES, generated
from support import check, check_equal, check_in

from riscv_tools.board_equivalence import HandWritten, compare
from riscv_tools.board_equivalence.core import pins_of

HAND = FIXTURES / "handwritten"
NAME = "de0_cv_de0_cv"


def _hand() -> HandWritten:
    """Read the files written by hand, as in Insper-RISC-V."""
    return HandWritten(
        (HAND / "de0-cv.qsf").read_text(),
        (HAND / "de0-cv.sdc").read_text(),
        (HAND / "sdram_platform_pll.v").read_text(),
    )


def _generated() -> HandWritten:
    """Read the files the generator writes for the DE0-CV."""
    files = generated("de0-cv").files
    return HandWritten(
        files[f"{NAME}.qsf"], files[f"{NAME}.sdc"], files[f"{NAME}_pll.v"]
    )


def _report():
    """Compare with the PLL module renamed."""
    return compare(
        _hand(), _generated(), {"sdram_platform_pll": f"{NAME}_pll"}
    )


def test_pins_assignments_project_constraints_and_pll_are_equivalent() -> None:
    """Pins, assignments, constraints and the PLL all match."""
    report = _report()
    for name in ("pins", "assignments", "project", "constraints", "pll"):
        section = report.section(name)
        check(section.equivalent, f"{name}: {section}")
        check_equal(section.only_handwritten, [])
        check_equal(section.changed, [])


def test_the_pin_count_is_the_one_of_the_handwritten_qsf() -> None:
    """107 active pin assignments, as the board package check found."""
    check_equal(len(pins_of(_hand().qsf)), 107)
    check_equal(pins_of(_hand().qsf), pins_of(_generated().qsf))


def test_the_only_extras_are_the_false_paths_of_the_new_ports() -> None:
    """The generated SDC also frees the switches and keys."""
    extra = _report().section("constraints").only_generated
    check_equal(len(extra), 2)
    check_in("set_false_path -from [get_ports {SW[*]}]", extra)


def test_the_sources_differ_only_by_the_files_replaced() -> None:
    """Without a closure the report lists the sources of the old top."""
    report = _report().section("sources")
    check_in("de0-cv_top.vhd", " ".join(report.only_handwritten))
    check_in("de0_cv_de0_cv_top.vhd", " ".join(report.only_generated))


def test_a_changed_pin_is_reported() -> None:
    """Moving one pin shows as a change on that signal."""
    gen = _generated()
    moved = gen.qsf.replace(
        "set_location_assignment PIN_M9 -to CLOCK_50",
        "set_location_assignment PIN_M10 -to CLOCK_50",
    )
    report = compare(
        _hand(),
        HandWritten(moved, gen.sdc, gen.pll),
        {"sdram_platform_pll": f"{NAME}_pll"},
    )
    check_equal(
        report.section("pins").changed,
        ["CLOCK_50: M9 / 3.3-V LVTTL -> M10 / 3.3-V LVTTL"],
    )
    check(not report.equivalent)


def test_a_changed_phase_or_constraint_is_reported() -> None:
    """A PLL phase and an SDC delay both show up."""
    gen = _generated()
    report = compare(
        _hand(),
        HandWritten(
            gen.qsf,
            gen.sdc.replace("-max 1.5", "-max 1.6"),
            gen.pll.replace('"4000 ps"', '"3875 ps"'),
        ),
        {"sdram_platform_pll": f"{NAME}_pll"},
    )
    check(report.section("pll").changed)
    check(report.section("constraints").only_handwritten)
    check_in("[pll] DIFFERENT", report.render())
