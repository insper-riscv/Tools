"""Generates a golden RAM reference via Spike, and manages the Spike build."""

from .core import generate_golden, write_golden_json
from .setup import setup, update

__all__ = ["generate_golden", "setup", "update", "write_golden_json"]
