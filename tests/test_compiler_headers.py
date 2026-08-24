from riscv_tools.compiler.__config__ import DEFAULTS
from riscv_tools.compiler.headers import canonical_march, parse_header

ISA = DEFAULTS["isa"]


def test_canonical_march_no_ext():
    assert canonical_march(ISA, "") == "rv32i"


def test_canonical_march_single_ext():
    assert canonical_march(ISA, "M") == "rv32im"


def test_canonical_march_order_independent():
    assert canonical_march(ISA, "M,A") == canonical_march(ISA, "A,M")
    assert canonical_march(ISA, "A,M") == "rv32ima"


def test_parse_header_defaults():
    march, kind, timeout_s = parse_header(ISA, 15, "int main(void) { return 0; }")
    assert march == "rv32i"
    assert kind == "unit"
    assert timeout_s == 15.0


def test_parse_header_all_fields():
    text = "// RV32_EXT: M\n// RV32_TEST_KIND: memory\n// RV32_TIMEOUT_S: 30\n"
    march, kind, timeout_s = parse_header(ISA, 15, text)
    assert march == "rv32im"
    assert kind == "memory"
    assert timeout_s == 30.0
