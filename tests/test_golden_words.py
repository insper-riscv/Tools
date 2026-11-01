"""Tests for the word-grouped golden (no Spike or GCC needed)."""

import pytest

from riscv_tools.golden_generator import group_words, word_range

BYTES = {0x10 + i: 0x11 * (i + 1) for i in range(8)}


def test_group_words_joins_32_bits_little_endian() -> None:
    """Group words joins 4 bytes into one little-endian word."""
    assert group_words(BYTES, 4) == {0x10: 0x44332211, 0x14: 0x88776655}


def test_group_words_joins_64_bits_little_endian() -> None:
    """Group words joins 8 bytes into one little-endian word."""
    assert group_words(BYTES, 8) == {0x10: 0x8877665544332211}


def test_group_words_rejects_an_incomplete_word() -> None:
    """Group words rejects a word that lacks some of its bytes."""
    with pytest.raises(ValueError, match="all of its 8 bytes"):
        group_words({0x10 + i: 1 for i in range(4)}, 8)


def test_word_range_rounds_the_end_up() -> None:
    """Word range rounds the end up to whole words."""
    assert word_range((0x10, 0x15), 4) == (0x10, 0x18)
    assert word_range((0x10, 0x15), 8) == (0x10, 0x18)
    assert word_range((0x10, 0x20), 8) == (0x10, 0x20)


def test_word_range_rejects_an_unaligned_start() -> None:
    """Word range rejects a start that is not a multiple of the size."""
    with pytest.raises(ValueError, match="not aligned"):
        word_range((0x14, 0x20), 8)
