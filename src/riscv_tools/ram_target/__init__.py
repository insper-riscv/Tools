"""Where a project's RAM lives and how the host reaches it over JTAG."""

from .core import (
    RamTarget,
    SdramDebugRam,
    read_words,
    sparse_mif_words,
    target_from_config,
    write_word,
)

__all__ = [
    "RamTarget",
    "SdramDebugRam",
    "read_words",
    "sparse_mif_words",
    "target_from_config",
    "write_word",
]
