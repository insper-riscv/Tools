"""Compiles bare-metal test sources (.c/.S) into linked .elf/.bin."""

from .build import compile_test
from .headers import canonical_march, parse_header

__all__ = ["canonical_march", "compile_test", "parse_header"]
