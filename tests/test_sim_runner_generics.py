"""Tests for the generics that a simulation passes to its toplevel."""

from pathlib import Path

from support import check_equal, check_is

from riscv_tools.sim_runner.generics import (
    declared_generics,
    without_undeclared_off,
)

_TOP = """\
-- generic (ghost : string);
entity top is
    generic (
        boot_file, other_file : string  := "a.hex";  -- a comment
        width                 : natural := 8;
        enabled               : boolean := true
    );
    port (
        i_clk : in std_logic
    );
end entity top;
"""


def _write(tmp_path: Path, name: str, text: str) -> str:
    """Write a VHDL file and return its path."""
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_the_generics_of_the_toplevel_are_listed_in_lowercase(
    tmp_path: Path,
) -> None:
    """Comma lists count, comments and the port clause do not."""
    top = _write(tmp_path, "top.vhd", _TOP)
    check_equal(
        declared_generics([top], "TOP"),
        {"boot_file", "other_file", "width", "enabled"},
    )


def test_a_toplevel_that_is_in_no_file_is_unknown(tmp_path: Path) -> None:
    """Nothing is assumed about an entity that no source declares."""
    other = _write(tmp_path, "other.vhd", "entity other is end entity other;")
    check_is(declared_generics([other, "missing.vhd"], "top"), None)


def test_an_off_parameter_that_the_toplevel_lacks_is_not_passed() -> None:
    """`ROM_FILE: false` stays out when the top has no `rom_file`."""
    declared = {"width", "enabled"}
    passed = without_undeclared_off(
        {"ROM_FILE": False, "rom_addr_width": "false", "width": 16},
        declared,
    )
    check_equal(passed, {"width": 16})


def test_an_off_parameter_that_the_toplevel_has_is_passed() -> None:
    """A boolean generic set to false is a value of the generic."""
    declared = {"enabled", "width"}
    passed = without_undeclared_off({"ENABLED": False, "width": 4}, declared)
    check_equal(passed, {"ENABLED": False, "width": 4})


def test_an_enabled_parameter_is_always_passed() -> None:
    """GHDL reports an enabled generic that the top does not have."""
    passed = without_undeclared_off({"ROM_FILE": "x.hex"}, {"width"})
    check_equal(passed, {"ROM_FILE": "x.hex"})


def test_without_the_top_generics_every_parameter_is_passed() -> None:
    """Unknown generics of the toplevel keep the old behavior."""
    parameters = {"ROM_FILE": False, "width": 1}
    check_equal(without_undeclared_off(parameters, None), parameters)
