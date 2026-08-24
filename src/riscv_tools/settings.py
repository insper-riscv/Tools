"""Assembles the merged config dict every other module's functions
take as `cfg`. Each module owns its own defaults (its `__config__.py`
DEFAULTS dict) — this just deep-merges all of them together and then
layers the consuming project's own config.yaml on top, which always
wins. Add a new module's DEFAULTS to _MODULE_DEFAULTS to wire it in.
"""
from pathlib import Path

import yaml

from riscv_tools.compiler.__config__ import DEFAULTS as _COMPILER_DEFAULTS
from riscv_tools.jtag.__config__ import DEFAULTS as _JTAG_DEFAULTS
from riscv_tools.mailbox.__config__ import DEFAULTS as _MAILBOX_DEFAULTS
from riscv_tools.orchestrator.__config__ import DEFAULTS as _ORCHESTRATOR_DEFAULTS
from riscv_tools.quartus_program.__config__ import DEFAULTS as _QUARTUS_PROGRAM_DEFAULTS
from riscv_tools.ram_dump.__config__ import DEFAULTS as _RAM_DUMP_DEFAULTS
from riscv_tools.ram_zero.__config__ import DEFAULTS as _RAM_ZERO_DEFAULTS
from riscv_tools.rom_writer.__config__ import DEFAULTS as _ROM_WRITER_DEFAULTS

_MODULE_DEFAULTS = [
    _COMPILER_DEFAULTS,
    _JTAG_DEFAULTS,
    _ROM_WRITER_DEFAULTS,
    _RAM_ZERO_DEFAULTS,
    _RAM_DUMP_DEFAULTS,
    _MAILBOX_DEFAULTS,
    _QUARTUS_PROGRAM_DEFAULTS,
    _ORCHESTRATOR_DEFAULTS,
]


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merges overlay into base (overlay wins on
    conflicts); returns a new dict, doesn't mutate either argument."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(project_config_path: Path) -> dict:
    """Merges every module's DEFAULTS (in _MODULE_DEFAULTS order) and
    then the project's own config.yaml on top."""
    cfg: dict = {}
    for defaults in _MODULE_DEFAULTS:
        cfg = deep_merge(cfg, defaults)
    project_cfg = yaml.safe_load(Path(project_config_path).read_text())
    return deep_merge(cfg, project_cfg)
