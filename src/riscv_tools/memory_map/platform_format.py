"""Read the blocks of a platform YAML into what the Tools use inside.

A platform file describes the core (`core`), the memories (`memory`) and
the peripherals (`peripherals`) in blocks. `normalize` derives from them
the profile and extras (see `riscv_tools.memory_map.core_profile`) and
the regions, the four memory choices and the list of peripherals (see
`riscv_tools.memory_map.layout`), and refuses the keys they replace.
"""

from pathlib import Path
from typing import Any

from riscv_tools.memory_map.core_profile import normalize as normalize_core
from riscv_tools.memory_map.groups import resolve as resolve_groups
from riscv_tools.memory_map.layout import normalize_layout


def normalize(
    data: dict[str, Any], platform_file: Path, *, replaced: bool = False
) -> None:
    """Derive the internal keys of a platform just read.

    Parameters
    ----------
    data : dict of {str: Any}
        The platform as read, changed in place.
    platform_file : Path
        The platform YAML, which `profiles` is relative to.
    replaced : bool, optional
        True when `--profile` replaces the profile.

    Raises
    ------
    ValueError
        If a block is not valid or an old key is still there.
    """
    normalize_core(data, platform_file, replaced=replaced)
    normalize_layout(data)
    resolve_groups(data, platform_file)
