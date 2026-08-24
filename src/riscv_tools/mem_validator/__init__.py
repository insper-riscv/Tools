"""Compares a RAM dump against a golden JSON of expected byte values."""

from .core import compare, parse_mif_words, words_to_bytes

__all__ = ["compare", "parse_mif_words", "words_to_bytes"]
