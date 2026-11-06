"""fit_estimate: policy, table, estimator and V11 to V14, V18."""

import argparse
import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check, check_equal, check_in

from riscv_tools import fit_estimate as fe
from riscv_tools import quartus_reports as qr
from riscv_tools.cli.calibrate_cmd import cmd_check_fit

RESOURCES: dict[str, Any] = {
    "logic": {"unit": "le", "total": 22320},
    "block_ram": {"kind": "m9k", "blocks": 66, "bits_per_block": 9216},
    "multipliers": {"kind": "dsp9x9", "total": 132},
    "plls": 4,
    "user_pins": 153,
}
CAPACITY = fe.capacity_from_resources(RESOURCES)


def fictional_table(
    max_pct: float | None = 4.0, core: float = 6000.0
) -> fe.CalibrationTable:
    """Build a table of made-up coefficients in LEs."""
    coefficients: dict[str, float | None] = {
        "core.rv32i": core,
        "extensions.Zicsr": 300.0,
        "extensions.Zmmul": 500.0,
        "extensions.M": 900.0,
        "zihpm.a0": 100.0,
        "zihpm.a1": 20.0,
        "zihpm.a2": 1.0,
        "cache.icache.c0": 0.0,
        "cache.icache.c1": 2.0,
        "cache.dcache.c0": 0.0,
        "cache.dcache.c1": 3.0,
    }
    return fe.CalibrationTable(
        "fictional",
        "le",
        coefficients,
        error={"max_pct": max_pct, "map_to_fit_ratio": None},
    )


@pytest.mark.parametrize(
    "used, expected",
    [
        (85, fe.Level.PASS),
        (86, fe.Level.WARN),
        (100, fe.Level.WARN),
        (101, fe.Level.ERROR),
    ],
)
def test_the_policy_thresholds(used: int, expected: fe.Level) -> None:
    """Up to 85 % passes, up to 100 % warns, above is an error."""
    check_equal(fe.classify(used, 100), expected)


def test_the_policy_has_no_option_to_force() -> None:
    """The policy and the estimator take no force option."""
    for func in (fe.classify, fe.estimate, fe.report_findings):
        names = inspect.signature(func).parameters
        check(not any("force" in name for name in names), func.__name__)


def test_capacity_needs_every_resource() -> None:
    """Capacity needs every resource."""
    with pytest.raises(ValueError, match="incomplete"):
        fe.capacity_from_resources({"logic": {"unit": "le"}})
    check_equal(CAPACITY.ram_bits, 66 * 9216)


def test_the_terms_apply_the_isa_implications() -> None:
    """Zicntr implies Zicsr, M implies Zmmul, Sscofpmf needs a base."""
    spec = fe.ProfileSpec(
        extensions=frozenset({"M", "Zicntr"}),
        extras=frozenset({"Sscofpmf"}),
    )
    values = fe.terms(spec)
    check_in("extensions.Zicsr", values)
    check_in("extensions.Zmmul", values)
    check_in("extensions.M", values)
    check("extras.Sscofpmf" not in values)


def test_the_estimate_adds_the_terms_of_the_table() -> None:
    """The estimate adds the terms of the table."""
    spec = fe.ProfileSpec(
        extensions=frozenset({"M", "Zihpm"}),
        hpm_counters=4,
        hpm_width=40,
        icache_kbit=32,
        dcache_kbit=32,
    )
    total, missing = fe.estimate_logic(spec, fictional_table(), 9216)
    expected = 6000 + 300 + 500 + 900 + (100 + 80 + 160) + 64 + 96
    check_equal(total, expected)
    check_equal(missing, ())


def test_a_null_coefficient_is_reported_as_missing() -> None:
    """A null coefficient is reported as missing."""
    table = fictional_table()
    table.coefficients["extensions.Zicsr"] = None
    spec = fe.ProfileSpec(extensions=frozenset({"Zicsr"}))
    _, missing = fe.estimate_logic(spec, table, 9216)
    check_equal(missing, ("extensions.Zicsr",))


def test_blocks_follow_the_formula() -> None:
    """Blocks are the memory ceilings plus caches and registers."""
    spec = fe.ProfileSpec(
        emulated_bytes=(4096, 1000),
        icache_kbit=32,
        register_blocks=2,
    )
    # 32768 bits = 4 blocks de 9216 (3,55), 8000 = 1, 32768 = 4, + 2
    check_equal(fe.blocks_needed(spec, 9216), 4 + 1 + 4 + 2)


def test_logic_above_capacity_is_v12_and_fails() -> None:
    """Estimated logic above the capacity is V12, an error."""
    spec = fe.ProfileSpec(extensions=frozenset({"M"}))
    table = fictional_table(core=25100.0)
    result = fe.estimate(spec, table, CAPACITY, "de0-nano")
    check(not result.ok)
    message = result.findings[-1].message
    check(message.startswith("E estimated logic "), message)
    check_in("exceeds 22,320 LE on 'de0-nano'", message)
    check_in("expected error 4%", message)


def test_logic_between_85_and_100_percent_is_v13() -> None:
    """Estimated logic between 85 % and 100 % is a V13 warning."""
    spec = fe.ProfileSpec()
    table = fictional_table(core=20400.0)
    result = fe.estimate(spec, table, CAPACITY, "de0-nano")
    check(result.ok)
    codes = [item.code for item in result.findings]
    check_equal(codes, ["V13"])
    check_in("only the fit decides", result.findings[0].message)


def test_emulated_memory_over_the_blocks_is_v11() -> None:
    """Emulated memory over the blocks of the device is V11."""
    spec = fe.ProfileSpec(emulated_bytes=(75 * 1152,))
    result = fe.estimate(spec, fictional_table(), CAPACITY, "de0-nano")
    first = result.findings[0]
    check_equal(first.code, "V11")
    check_equal(
        first.message,
        "E emulated memory needs 75 blocks above the 66 available on "
        "'de0-nano' (utilization 1.14)",
    )


def test_an_empty_table_only_emits_v18() -> None:
    """With an empty table the estimator only emits V18."""
    table = fe.empty_table("max-10", "le")
    result = fe.estimate(fe.ProfileSpec(), table, CAPACITY, "de10-lite")
    check_equal([item.code for item in result.findings], ["V18"])
    check_equal(
        result.findings[0].message,
        "W family 'max-10' has no calibration; capacity estimate skipped, "
        "only the fit decides",
    )
    check(result.ok and result.logic is None)


def test_an_unvalidated_family_does_not_fail_on_logic() -> None:
    """A family above 10 % error stays a warning even over capacity."""
    spec = fe.ProfileSpec()
    table = fictional_table(12.0, core=25000.0)
    result = fe.estimate(spec, table, CAPACITY, "x")
    check(result.ok)
    check_in("V18", [item.code for item in result.findings])


def test_the_ratio_converts_the_estimate_to_the_fit() -> None:
    """The ratio fit / synthesis scales the estimate."""
    table = fictional_table()
    table.error["map_to_fit_ratio"] = 0.5
    result = fe.estimate(fe.ProfileSpec(), table, CAPACITY, "x")
    check_equal(result.logic, 3000.0)


def test_the_report_lists_every_exceeded_resource_at_once() -> None:
    """The report check lists every exceeded resource at once."""
    usage = qr.parse_summary(
        "Fitter Status : Successful - x\n"
        "Total logic elements : 22,901 / 22,320 ( 103 % )\n"
        "Total pins : 120 / 153 ( 78 % )\n"
        "Total memory bits : 612,000 / 608,256 ( 101 % )\n"
        "Embedded Multiplier 9-bit elements : 140 / 132 ( 106 % )\n"
        "Total PLLs : 2 / 4 ( 50 % )\n"
    )
    findings = fe.report_findings(usage, CAPACITY)
    errors = [item for item in findings if item.severity == "E"]
    check_equal(len(errors), 1)
    check_equal(
        errors[0].message,
        "E fit report exceeds: logic LE 22,901/22,320; "
        "RAM bits 612,000/608,256; multipliers 140/132",
    )


def test_a_report_inside_the_capacity_passes_with_a_slack_warning() -> None:
    """A report between 85 % and 100 % only warns."""
    usage = qr.parse_summary(
        "Fitter Status : Successful - x\n"
        "Total logic elements : 20,400 / 22,320 ( 91 % )\n"
    )
    findings = fe.report_findings(usage)
    check_equal([item.severity for item in findings], ["W"])


def test_the_table_is_read_from_a_file_and_the_vocabulary_is_enforced(
    tmp_path: Path,
) -> None:
    """The table is a file; a key outside the catalogs is refused."""
    path = tmp_path / "t.yaml"
    data: dict[str, Any] = {
        "family": "cyclone-v",
        "unit": "alm",
        "coefficients": {"extensions": {"Zicsr": 12, "M": None}},
        "error": {"max_pct": 3},
    }
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    table = fe.load_table(path, fe.DEFAULT_VOCABULARY)
    check_equal(table.coefficients["extensions.Zicsr"], 12.0)
    check(table.logic_error_enabled)
    data["coefficients"]["extensions"]["Zbb"] = 1
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="not in the catalogs"):
        fe.load_table(path, fe.DEFAULT_VOCABULARY)
    data["unit"] = "lut"
    with pytest.raises(ValueError, match="unit"):
        fe.table_from_mapping(data)


def test_flatten_and_nest_are_inverse() -> None:
    """Flatten and nest are inverse."""
    nested = {"core": {"rv32i": 1.0}, "cache": {"icache": {"c1": 2.0}}}
    check_equal(fe.nest(fe.flatten(nested)), nested)


def test_check_fit_command_fails_on_an_exceeded_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`check-fit` exits 1 and lists the exceeded resources."""
    (tmp_path / "x.fit.summary").write_text(
        "Fitter Status : Successful - x\n"
        "Total logic elements : 22,901 / 22,320 ( 103 % )\n",
        encoding="utf-8",
    )
    board = tmp_path / "board.yaml"
    board.write_text(yaml.safe_dump({"resources": RESOURCES}))
    args = argparse.Namespace(
        reports=".", board="board.yaml", root=str(tmp_path), config=None
    )
    with pytest.raises(SystemExit) as raised:
        cmd_check_fit(args)
    check_equal(raised.value.code, 1)
    check_in(
        "fit report exceeds: logic LE 22,901/22,320", capsys.readouterr().err
    )
