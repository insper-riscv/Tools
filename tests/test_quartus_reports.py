"""quartus_reports: summaries and tables of the Quartus."""

from pathlib import Path

import pytest
from support import check, check_equal

from riscv_tools import quartus_reports as qr

FIXTURES = Path(__file__).parent / "fixtures" / "quartus_reports"
CYCLONE_V = FIXTURES / "cyclone-v"
# Resumo de ajuste fictício de uma família de elementos lógicos.
LE_FIT = """Fitter Status : Successful - Mon Jan  5 10:00:00 2026
Quartus Prime Version : 25.1std.0 Build 1129 10/21/2025 SC Lite Edition
Revision Name : demo
Top-level Entity Name : top
Family : Cyclone IV E
Device : EP4CE22F17C6
Total logic elements : 22,901 / 22,320 ( 103 % )
Total registers : 9000
Total pins : 120 / 153 ( 78 % )
Total virtual pins : 0
Total memory bits : 612,000 / 608,256 ( 101 % )
Embedded Multiplier 9-bit elements : 140 / 132 ( 106 % )
Total PLLs : 2 / 4 ( 50 % )
"""


def read(name: str) -> str:
    """Read a fixture of the Cyclone V."""
    return (CYCLONE_V / name).read_text(encoding="utf-8")


def test_the_fit_summary_gives_each_resource_with_its_capacity() -> None:
    """The fit summary gives each resource with its capacity."""
    usage = qr.parse_summary(read("core_fpga_sdram.fit.summary"))
    check_equal(usage.logic_unit, "alm")
    check_equal(usage.logic, qr.Quantity(4354, 18480))
    check_equal(usage.ram_bits, qr.Quantity(544768, 3153920))
    check_equal(usage.ram_blocks, qr.Quantity(72, 308))
    check_equal(usage.multipliers, qr.Quantity(0, 66))
    check_equal(usage.plls, qr.Quantity(1, 4))
    check_equal(usage.pins, qr.Quantity(93, 224))
    check_equal(usage.meta["device"], "5CEBA4F23C7")
    check(qr.succeeded(usage))


def test_the_synthesis_summary_has_no_logic_line() -> None:
    """The synthesis summary leaves the logic as N/A."""
    usage = qr.parse_summary(read("core_fpga_sdram.map.summary"))
    check(usage.logic is None)
    check_equal(usage.pins, qr.Quantity(93, None))


def test_the_map_report_gives_the_alm_estimate() -> None:
    """The map report gives the ALM estimate and the project's PLLs."""
    usage = qr.parse_map_report(
        read("core_fpga_sdram.map.rpt"), read("core_fpga_sdram.map.summary")
    )
    check_equal(usage.logic, qr.Quantity(4638, None))
    check_equal(usage.logic_unit, "alm")
    check_equal(usage.registers, 5191)
    check_equal(usage.plls, qr.Quantity(1, None))
    check_equal(usage.meta["version"][:11], "25.1std.0 B")


def test_the_hierarchy_is_read_with_its_depth() -> None:
    """The hierarchy is read with its depth."""
    usage = qr.parse_map_report(read("core_fpga_sdram.map.rpt"))
    top = usage.entities[0]
    check_equal((top.name, top.depth, top.luts), ("core_fpga_sdram", 0, 5909))
    child = usage.entities[1]
    check_equal((child.depth, child.memory_bits), (1, 16384))


def test_a_logic_element_family_is_read_too() -> None:
    """A logic element family is read in LE and 9-bit multipliers."""
    usage = qr.parse_summary(LE_FIT)
    check_equal(usage.logic_unit, "le")
    check_equal(usage.logic, qr.Quantity(22901, 22320))
    check_equal(usage.multipliers, qr.Quantity(140, 132))
    check_equal(usage.ram_bits, qr.Quantity(612000, 608256))


def test_the_fit_report_table_is_the_fallback() -> None:
    """The fit report table is read when no summary exists."""
    table = (
        "; Fitter Resource Usage Summary                    ;\n"
        "+------+------+-----+\n"
        "; Resource ; Usage ; % ;\n"
        "+------+------+-----+\n"
        "; Logic utilization (ALMs needed / total ALMs on device) "
        "; 4,354 / 18,480 ; 24 % ;\n"
        "; I/O pins ; 93 / 224 ; 42 % ;\n"
        "+------+------+-----+\n"
    )
    usage = qr.parse_fit_report(table)
    check_equal(usage.logic, qr.Quantity(4354, 18480))
    check_equal(usage.pins, qr.Quantity(93, 224))


@pytest.mark.parametrize("text", ["", "nothing here\n"])
def test_a_file_without_resources_is_an_error(text: str) -> None:
    """A file without resource lines is an error."""
    with pytest.raises(ValueError, match="no "):
        qr.parse_summary(text)
    with pytest.raises(ValueError, match="no "):
        qr.parse_map_report(text)
    with pytest.raises(ValueError, match="no "):
        qr.parse_fit_report(text)
