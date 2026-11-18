"""Finds the Quartus of the machine and puts it on the PATH."""

from riscv_tools.quartus_root.core import (
    DEFAULT_ROOT,
    DEFAULT_VERSION,
    ROOT_VAR,
    VERSION_VAR,
    bin_dir,
    prepend_to_path,
)

__all__ = [
    "DEFAULT_ROOT",
    "DEFAULT_VERSION",
    "ROOT_VAR",
    "VERSION_VAR",
    "bin_dir",
    "prepend_to_path",
]
