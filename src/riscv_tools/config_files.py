"""Leitura de arquivos de configuração com a cadeia `extends:`.

Módulo leve, sem dependência dos módulos de domínio, para que o
catálogo de placas leia seus arquivos sem puxar a configuração de todos
os módulos (ver `riscv_tools.settings`).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.memory_map.config_view import config_from_platform


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
    return read_project_config(Path(path), ())


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
    return read_project_config(Path(path), (), base_of)


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


def read_project_config(
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

    base = read_project_config(
        base_of(path, str(base_ref)), (*chain, resolved), base_of
    )
    return deep_merge(base, data)
