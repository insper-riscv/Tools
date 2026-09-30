"""Check that every file path a project references exists."""

from .core import check_paths, collect

__all__ = ["check_paths", "collect"]
