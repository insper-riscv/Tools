"""Assemble the merged config dict that functions take as `cfg`.

Each module owns its own defaults (its `__config__.py` DEFAULTS
dict), this just deep-merges all of them together and then layers the
consuming project's own config.yaml on top, which always wins. Add a
new module's DEFAULTS to _MODULE_DEFAULTS to wire it in.
"""

from pathlib import Path
from typing import Any

from riscv_tools.c_to_asm.__config__ import DEFAULTS as _C_TO_ASM_DEFAULTS
from riscv_tools.certify.__config__ import DEFAULTS as _CERTIFY_DEFAULTS
from riscv_tools.compiler.__config__ import DEFAULTS as _COMPILER_DEFAULTS
from riscv_tools.config_files import deep_merge, read_project_config
from riscv_tools.golden_generator.__config__ import (
    DEFAULTS as _GOLDEN_GENERATOR_DEFAULTS,
)
from riscv_tools.htif.__config__ import DEFAULTS as _HTIF_DEFAULTS
from riscv_tools.jtag.__config__ import DEFAULTS as _JTAG_DEFAULTS
from riscv_tools.orchestrator.__config__ import (
    DEFAULTS as _ORCHESTRATOR_DEFAULTS,
)
from riscv_tools.quartus_program.__config__ import (
    DEFAULTS as _QUARTUS_PROGRAM_DEFAULTS,
)
from riscv_tools.ram_dump.__config__ import DEFAULTS as _RAM_DUMP_DEFAULTS
from riscv_tools.ram_zero.__config__ import DEFAULTS as _RAM_ZERO_DEFAULTS
from riscv_tools.rom_writer.__config__ import DEFAULTS as _ROM_WRITER_DEFAULTS
from riscv_tools.run_log.__config__ import DEFAULTS as _RUN_LOG_DEFAULTS
from riscv_tools.sim_runner.__config__ import DEFAULTS as _SIM_RUNNER_DEFAULTS

_MODULE_DEFAULTS = [
    _COMPILER_DEFAULTS,
    _C_TO_ASM_DEFAULTS,
    _JTAG_DEFAULTS,
    _ROM_WRITER_DEFAULTS,
    _RAM_ZERO_DEFAULTS,
    _RAM_DUMP_DEFAULTS,
    _HTIF_DEFAULTS,
    _GOLDEN_GENERATOR_DEFAULTS,
    _QUARTUS_PROGRAM_DEFAULTS,
    _ORCHESTRATOR_DEFAULTS,
    _SIM_RUNNER_DEFAULTS,
    _CERTIFY_DEFAULTS,
    _RUN_LOG_DEFAULTS,
]


def load_config(project_config_path: Path) -> dict[str, Any]:
    """Merge every module's DEFAULTS, then the project's config.yaml.

    Parameters
    ----------
    project_config_path : Path
        Path to the consuming project's own config.yaml (memory map,
        Quartus project paths, toolchain, etc.).

    Returns
    -------
    dict of {str: Any}
        The fully merged config dict, in the same nested shape every
        module's functions expect as `cfg` (top-level keys like
        "toolchain", "isa", "paths", "quartus", "memory", "emulator").
    """
    cfg: dict[str, Any] = {}

    for defaults in _MODULE_DEFAULTS:
        cfg = deep_merge(cfg, defaults)

    return deep_merge(cfg, read_project_config(Path(project_config_path), ()))
