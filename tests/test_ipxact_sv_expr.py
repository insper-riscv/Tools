"""Tests for the SystemVerilog expression evaluator of ipxact."""

import pytest
from support import check_equal

from riscv_tools.ipxact.sv_expr import (
    ExpressionError,
    evaluate_with,
    identifiers,
)

NAMES = {"data_width": 8, "n": 5, "flag": 1}


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("7", 7),
        ("(data_width - 1)", 7),
        ("((2 ** n) - 1)", 31),
        ("2 ** 3 ** 2", 512),
        ("-3 + 5", 2),
        ("7 / 2", 3),
        ("-7 / 2", -3),
        ("-7 % 3", -1),
        ("(flag ? 10 : 20)", 10),
        ("(n > 4 && flag == 1)", 1),
        ("(n < 4 || flag != 1)", 0),
        ("8'hFF", 255),
        ("4'b1010", 10),
        ("1'b0", 0),
        ("$clog2(n) + $clog2(1)", 3),
        ("$clog2(data_width)", 3),
    ],
)
def test_evaluate(text: str, value: int) -> None:
    """The evaluator follows the precedence of SystemVerilog."""
    check_equal(evaluate_with(text, NAMES), value)


@pytest.mark.parametrize(
    "text", ["", "1 +", "(1", "1 2", "unknown", "3 $ 4", "1 / 0"]
)
def test_malformed(text: str) -> None:
    """A malformed or unresolvable expression is refused."""
    with pytest.raises(ExpressionError):
        evaluate_with(text, NAMES)


def test_identifiers() -> None:
    """The names of an expression come out in order of appearance."""
    check_equal(
        list(identifiers("(a_1 + b) * 8'hFF - a_1")), ["a_1", "b", "a_1"]
    )
