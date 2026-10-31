"""Compares a RAM dump against a golden JSON of expected byte values."""

from riscv_tools.mem_validator.core import (
    compare,
    compare_bytes,
    golden_word_offsets,
    load_golden,
    parse_mif_words,
    words_to_bytes,
)

__all__ = [
    "compare",
    "compare_bytes",
    "golden_word_offsets",
    "load_golden",
    "parse_mif_words",
    "words_to_bytes",
]
