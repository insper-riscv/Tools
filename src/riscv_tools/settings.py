"""Assemble the merged config dict every other module's functions take as `cfg`.

Each module owns its own defaults (its `__config__.py` DEFAULTS
dict), this just deep-merges all of them together and then layers the
consuming project's own config.yaml on top, which always wins. Add a
new module's DEFAULTS to _MODULE_DEFAULTS to wire it in.
"""

from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.c_to_asm.__config__ import DEFAULTS as _C_TO_ASM_DEFAULTS
from riscv_tools.compiler.__config__ import DEFAULTS as _COMPILER_DEFAULTS
from riscv_tools.freq_sweep.__config__ import DEFAULTS as _FREQ_SWEEP_DEFAULTS
from riscv_tools.golden_generator.__config__ import (
    DEFAULTS as _GOLDEN_GENERATOR_DEFAULTS,
)
from riscv_tools.jtag.__config__ import DEFAULTS as _JTAG_DEFAULTS
from riscv_tools.mailbox.__config__ import DEFAULTS as _MAILBOX_DEFAULTS
from riscv_tools.orchestrator.__config__ import DEFAULTS as _ORCHESTRATOR_DEFAULTS
from riscv_tools.quartus_program.__config__ import DEFAULTS as _QUARTUS_PROGRAM_DEFAULTS
from riscv_tools.ram_dump.__config__ import DEFAULTS as _RAM_DUMP_DEFAULTS
from riscv_tools.ram_zero.__config__ import DEFAULTS as _RAM_ZERO_DEFAULTS
from riscv_tools.rom_writer.__config__ import DEFAULTS as _ROM_WRITER_DEFAULTS
from riscv_tools.sim_runner.__config__ import DEFAULTS as _SIM_RUNNER_DEFAULTS

_MODULE_DEFAULTS = [
    _COMPILER_DEFAULTS,
    _C_TO_ASM_DEFAULTS,
    _JTAG_DEFAULTS,
    _ROM_WRITER_DEFAULTS,
    _RAM_ZERO_DEFAULTS,
    _RAM_DUMP_DEFAULTS,
    _MAILBOX_DEFAULTS,
    _GOLDEN_GENERATOR_DEFAULTS,
    _QUARTUS_PROGRAM_DEFAULTS,
    _ORCHESTRATOR_DEFAULTS,
    _SIM_RUNNER_DEFAULTS,
    _FREQ_SWEEP_DEFAULTS,
]


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into base (overlay wins on conflicts).

    Returns a new dict, doesn't mutate either argument.

    Parameters
    ----------
    base : dict of {str: Any}
        The starting dict, its own keys/values are used wherever
        overlay doesn't override them.
    overlay : dict of {str: Any}
        The dict to layer on top. For each key, if both base and
        overlay have a dict there, they're merged recursively;
        otherwise overlay's value wins outright (including replacing
        a base dict with a non-dict, or vice versa).

    Returns
    -------
    dict of {str: Any}
        A new dict combining base and overlay. Neither input is
        mutated.
    """
    result = dict(base)

    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            result[key] = deep_merge(
                cast(dict[str, Any], existing), cast(dict[str, Any], value)
            )
        else:
            result[key] = value

    return result


def load_config(project_config_path: Path) -> dict[str, Any]:
    """Merge every module's DEFAULTS (in order), then the project's own config.yaml.

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

    overlay: dict[str, Any] = yaml.safe_load(Path(project_config_path).read_text())
    return deep_merge(cfg, overlay)
