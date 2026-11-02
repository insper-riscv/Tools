"""Write a platform config for the project that consumes it."""

from riscv_tools.platform_sync.core import (
    PATH_KEYS,
    check_output,
    flatten,
    rebase,
    render,
    write_output,
)

__all__ = [
    "PATH_KEYS",
    "check_output",
    "flatten",
    "rebase",
    "render",
    "write_output",
]
