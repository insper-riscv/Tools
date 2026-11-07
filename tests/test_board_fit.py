"""Tests of the fit rule (V11 to V13) and of its report."""

from pathlib import Path
from typing import Any

import pytest
from catalog_support import (
    fresh_board,
    fresh_platform,
    write,
    write_catalog,
)
from support import check, check_equal

from riscv_tools.board_check import Finding, check_platform, fit_report
from riscv_tools.board_schema import Catalog

TABLE: dict[str, Any] = {
    "family": "fam",
    "unit": "le",
    "coefficients": {
        "core": {"rv32i": 400.0, "rv32e": 380.0},
        "extensions": {"Zicsr": 50.0},
        "cache": {
            "icache": {"c0": 0.0, "c1": 2.0},
            "dcache": {"c0": 0.0, "c1": 4.0},
        },
        "backends": {"sdram_16": 0.0},
        "per_block_glue": 1.0,
    },
    "error": {"rms_pct": 1.0, "max_pct": 2.0, "map_to_fit_ratio": 1.0},
}


def _fit_platform() -> dict[str, Any]:
    """Make a platform whose profile and caches the table prices."""
    platform = fresh_platform()
    platform["profile"] = "rv32i_zicsr"
    platform["regions"][1]["size"] = "28K"
    platform["flash"]["banks"] = [
        {"name": "A", "base": "0x1000", "size": "12K"},
        {"name": "B", "base": "0x4000", "size": "16K"},
    ]
    platform["memory"]["icache"] = {"enabled": True, "size_bits": 8192}
    platform["memory"]["dcache"] = {"enabled": True, "size_bits": 8192}
    return platform


def _board(logic: int = 1000, blocks: int = 100) -> dict[str, Any]:
    """Make the board with the capacities a test asks for."""
    board = fresh_board()
    board["resources"]["logic"]["total"] = logic
    board["resources"]["block_ram"]["blocks"] = blocks
    return board


def _run(
    root: Path,
    platform: dict[str, Any],
    board: dict[str, Any],
    table: dict[str, Any] | None = None,
) -> list[Finding]:
    """Lay out the catalog and the table, then check the platform."""
    write_catalog(root, board)
    write(root / "boards" / "calibration" / "fam.yaml", table or TABLE)
    return check_platform(platform, root)


def _texts(findings: list[Finding]) -> list[str]:
    """Format the findings as the messages the plan words."""
    return [str(finding) for finding in findings]


def test_a_reduced_profile_that_fits_gives_no_message(tmp_path: Path) -> None:
    """531 LEs and 35 blocks are far from the capacity."""
    check_equal(_run(tmp_path, _fit_platform(), _board()), [])


def test_blocks_above_the_capacity_are_an_error(tmp_path: Path) -> None:
    """The memories and the caches need more than the device has."""
    found = _texts(_run(tmp_path, _fit_platform(), _board(blocks=30)))
    check_equal(
        found,
        [
            "E emulated memory needs 35 blocks above the 30 available on"
            " 'bd' (utilization 1.17)"
        ],
    )


def test_blocks_between_85_and_100_percent_warn(tmp_path: Path) -> None:
    """Only the fit decides near the capacity."""
    found = _texts(_run(tmp_path, _fit_platform(), _board(blocks=40)))
    check_equal(
        found,
        [
            "W emulated memory needs 35 blocks, 88% of the 40 available on"
            " 'bd'; only the fit decides"
        ],
    )


def test_logic_above_the_capacity_is_an_error(tmp_path: Path) -> None:
    """The terms are 450 + 2 * 8 + 4 * 8 + 33 blocks = 531 LEs."""
    found = _texts(_run(tmp_path, _fit_platform(), _board(logic=400)))
    check_equal(len(found), 1)
    check(found[0].startswith("E estimated logic 531 LE exceeds 400 LE"))


def test_logic_near_the_capacity_warns(tmp_path: Path) -> None:
    """531 LEs of 620 is 86 %."""
    found = _texts(_run(tmp_path, _fit_platform(), _board(logic=620)))
    check_equal(len(found), 1)
    check(found[0].startswith("W estimated logic 531 LE is 86%"))


def test_a_platform_without_profile_is_not_estimated(tmp_path: Path) -> None:
    """The platforms written before the profile field keep passing."""
    platform = _fit_platform()
    del platform["profile"]
    check_equal(_run(tmp_path, platform, _board(logic=1, blocks=1)), [])


def test_an_invalid_table_is_a_v1_error(tmp_path: Path) -> None:
    """A table without the unit is refused, not ignored."""
    found = _run(tmp_path, _fit_platform(), _board(), {"family": "fam"})
    check_equal([item.rule for item in found], ["V1"])
    check("calibration of family 'fam'" in found[0].text)


@pytest.mark.parametrize("blocks", [100, 30])
def test_the_capacity_report(tmp_path: Path, blocks: int) -> None:
    """The report has the numbers of each resource and the findings."""
    write_catalog(tmp_path, _board(blocks=blocks))
    write(tmp_path / "boards" / "calibration" / "fam.yaml", TABLE)
    report, found = fit_report(
        _fit_platform(), "bd", Catalog.for_root(tmp_path)
    )
    if report is None:
        raise AssertionError("no report")
    check_equal(report["ram_blocks"]["estimated"], 35)
    check_equal(report["ram_blocks"]["total"], blocks)
    check_equal(
        report["logic"],
        {"estimated": 531, "total": 1000, "utilization": 0.531},
    )
    check_equal(len(report["findings"]), len(found))


def test_no_report_without_the_table(tmp_path: Path) -> None:
    """A family without the file has nothing to report."""
    write_catalog(tmp_path, _board())
    (tmp_path / "boards" / "calibration" / "fam.yaml").unlink()
    report, found = fit_report(
        _fit_platform(), "bd", Catalog.for_root(tmp_path)
    )
    check_equal(report, None)
    check_equal(found, [])
