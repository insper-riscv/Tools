"""Check that the `config_pkg` and the package of the map agree.

The first stage of the migration writes the constants that both packages
carry (the extensions, the caches, the externals, the memory map and the
slots) in both files. `check-memory-map` reads the two files of a
platform that asks for both (`generate.vhdl` and `generate.config_pkg`)
and fails when a constant has another value in each.
"""

import re
from pathlib import Path
from typing import Any, cast

from riscv_tools.memory_map.core import Mismatch, platform_dict
from riscv_tools.memory_map.profile import SWITCHES

# Pares do pacote do mapa e deste, com o fator do mapa em bytes.
COHERENT_PAIRS = (
    ("HAS_E", "IS_BASE_E", 1),
    ("HAS_ICACHE", "HAS_ICACHE", 1),
    ("HAS_DCACHE", "HAS_DCACHE", 1),
    ("ROM_EXTERNAL", "ROM_EXTERNAL", 1),
    ("RAM_EXTERNAL", "RAM_EXTERNAL", 1),
    ("BOOT_MEMORY_BITS", "BOOT_MEMORY_BITS", 1),
    ("CACHE_WINDOW_BITS", "CACHE_WINDOW_BITS", 1),
    ("ROM_BASE_KIB", "ROM_BASE", 1024),
    ("ROM_END_KIB", "ROM_END", 1024),
    ("RAM_BASE_KIB", "RAM_BASE", 1024),
    ("RAM_END_KIB", "RAM_END", 1024),
    ("EXT_BASE_KIB", "EXT_BASE", 1024),
    ("PERIPH_BASE_KIB", "PERIPH_BASE", 1024),
    ("PERIPH_SLOTS", "PERIPH_SLOTS", 1),
    *((key.upper(), key.upper(), 1) for key in SWITCHES),
)


_CONSTANT = re.compile(r"constant\s+(\w+)\s*:[^;=]*:=\s*([^;]*);", re.I)
_BIT_STRING = re.compile(r'x"([0-9A-F]+)"', re.I)


def _constants(text: str) -> dict[str, str]:
    """Read the value text of every constant of a VHDL file."""
    code = re.sub(r"--[^\n]*", "", text)
    return {
        name.upper(): value.strip() for name, value in _CONSTANT.findall(code)
    }


def _number(value: str) -> int | bool | None:
    """Read the value of a constant that this module writes.

    Parameters
    ----------
    value : str
        The text after `:=`.

    Returns
    -------
    int or bool or None
        A boolean, a natural, a hexadecimal address literal or a bit
        string of slots; None when the text is none of them.
    """
    if value in ("true", "false"):
        return value == "true"
    if value.isdecimal():
        return int(value)
    found = _BIT_STRING.search(value)
    if found:
        return int(found.group(1), 16)
    if re.fullmatch(r'"[01]+"', value):
        return int(value.strip('"'), 2)
    return None


def _disagrees(
    old: dict[str, str], new: dict[str, str]
) -> list[tuple[str, str, int | bool, int | bool]]:
    """List the constants that the two files carry with other values.

    Parameters
    ----------
    old : dict of {str: str}
        The constants of the package of the map.
    new : dict of {str: str}
        The constants of the `config_pkg`.

    Returns
    -------
    list of tuple of (str, str, int or bool, int or bool)
        The name in the map package, the name in the `config_pkg`, the
        value of the first (in bytes where it was in KiB) and the value
        of the second. A constant missing in either file, or of another
        kind, is not compared.
    """
    found: list[tuple[str, str, int | bool, int | bool]] = []
    for old_name, new_name, factor in COHERENT_PAIRS:
        a = _number(old.get(old_name, ""))
        b = _number(new.get(new_name, ""))
        if (
            a is None
            or b is None
            or isinstance(a, bool) != isinstance(b, bool)
        ):
            continue
        scaled = a if isinstance(a, bool) else a * factor
        if scaled != b:
            found.append((old_name, new_name, scaled, b))
    return found


def coherence_problems(platform: dict[str, Any], root: Path) -> list[Mismatch]:
    """Compare the `config_pkg` on disk with the package of the map.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform: `generate.vhdl` and `generate.config_pkg`
        give the two files.
    root : Path
        The project root the paths are relative to.

    Returns
    -------
    list of Mismatch
        A missing file, or a constant that has another value in the
        other file. Empty when the platform does not ask for both
        files.
    """
    wanted = platform_dict(platform, "generate")
    map_spec = cast(dict[str, Any], wanted.get("vhdl") or {})
    config_spec = cast(dict[str, Any], wanted.get("config_pkg") or {})
    if "path" not in map_spec or "path" not in config_spec:
        return []
    map_path, config_path = str(map_spec["path"]), str(config_spec["path"])
    missing = [
        Mismatch("config-pkg", path, "file not found")
        for path in (map_path, config_path)
        if not (root / path).is_file()
    ]
    if missing:
        return missing
    old = _constants((root / map_path).read_text(encoding="utf-8"))
    new = _constants((root / config_path).read_text(encoding="utf-8"))
    return [
        Mismatch(
            "config-pkg",
            config_path,
            f"{new_name} is {b!r} but {old_name} of {map_path} says {a!r}",
        )
        for old_name, new_name, a, b in _disagrees(old, new)
    ]
