"""Assemble the merged config dict that functions take as `cfg`.

Each module owns its own defaults (its `__config__.py` DEFAULTS
dict), this just deep-merges all of them together and then layers the
consuming project's own config.yaml on top, which always wins. Add a
new module's DEFAULTS to _MODULE_DEFAULTS to wire it in.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.c_to_asm.__config__ import DEFAULTS as _C_TO_ASM_DEFAULTS
from riscv_tools.certify.__config__ import DEFAULTS as _CERTIFY_DEFAULTS
from riscv_tools.compiler.__config__ import DEFAULTS as _COMPILER_DEFAULTS
from riscv_tools.golden_generator.__config__ import (
    DEFAULTS as _GOLDEN_GENERATOR_DEFAULTS,
)
from riscv_tools.htif.__config__ import DEFAULTS as _HTIF_DEFAULTS
from riscv_tools.jtag.__config__ import DEFAULTS as _JTAG_DEFAULTS
from riscv_tools.memory_map.config_view import config_from_platform
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


def deep_merge(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
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

    return deep_merge(cfg, _read_project_config(Path(project_config_path), ()))


def read_config(path: Path) -> dict[str, Any]:
    """Read one config file with its `extends:` chain resolved.

    Unlike `load_config`, it layers no module defaults, so the result is
    exactly what the files say.

    Parameters
    ----------
    path : Path
        The config file to read.

    Returns
    -------
    dict of {str: Any}
        The file's content merged over its bases.
    """
    return _read_project_config(Path(path), ())


def read_with_bases(
    path: Path, base_of: Callable[[Path, str], Path]
) -> dict[str, Any]:
    """Read one file with its `extends:` chain, naming the base by rule.

    The same merge as `read_config`, for a catalog whose files name
    their base by something other than a relative path (the chip
    catalog names the chip, and `base_of` turns the name into the file).

    Parameters
    ----------
    path : Path
        The file to read.
    base_of : Callable of (Path, str) to Path
        Receives the file that holds the `extends` key and its value,
        and returns the file of the base.

    Returns
    -------
    dict of {str: Any}
        The file's content merged over its bases, without `extends`.

    Raises
    ------
    ValueError
        The `extends` chain loops back to a file already in it.
    """
    return _read_project_config(Path(path), (), base_of)


def _relative_base(path: Path, ref: str) -> Path:
    """Name the base of a config as a path relative to the file.

    Parameters
    ----------
    path : Path
        The file that holds the `extends` key.
    ref : str
        The value of the key.

    Returns
    -------
    Path
        The file of the base.
    """
    return path.parent / ref


def _read_project_config(
    path: Path,
    chain: tuple[Path, ...],
    base_of: Callable[[Path, str], Path] = _relative_base,
) -> dict[str, Any]:
    """Read one project config file, resolving its `extends:` chain.

    `extends: <path>` (relative to the file that names it) makes that
    file the base this one is merged over, with the same rules as
    `deep_merge`, so a variant config only has to say what differs.
    `memory_map: <path>` names the platform map, whose addresses, sizes
    and memory address widths replace the ones the file would give.

    Parameters
    ----------
    path : Path
        The config file to read.
    chain : tuple of Path
        The files already being resolved, to reject a cycle.
    base_of : Callable of (Path, str) to Path, optional
        Turns the `extends` value into the file of the base; by
        default, a path relative to the file that names it.

    Returns
    -------
    dict of {str: Any}
        The file's content merged over its base, without the `extends`
        key.

    Raises
    ------
    ValueError
        The `extends` chain loops back to a file already in it.
    """
    resolved = path.resolve()
    if resolved in chain:
        loop = " -> ".join(str(p) for p in (*chain, resolved))
        raise ValueError(f"config `extends` loop: {loop}")

    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    base_ref = data.pop("extends", None)
    map_ref = data.pop("memory_map", None)
    if map_ref is not None:
        # the platform map is the single source of the addresses and
        # sizes, so it wins over what this file or its bases say
        data = deep_merge(
            data, config_from_platform(path.parent / str(map_ref))
        )
    if base_ref is None:
        return data

    base = _read_project_config(
        base_of(path, str(base_ref)), (*chain, resolved), base_of
    )
    return deep_merge(base, data)
