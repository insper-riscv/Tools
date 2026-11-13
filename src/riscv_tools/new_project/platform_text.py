"""Write the `platform.yaml` of a new project from the template's.

The template's file is edited line by line, so its comments and its
layout stay. A line the edit needs but the template does not have is
an error: the template then has a shape this module does not know.
"""

import re
from collections.abc import Callable
from typing import Any, cast

import yaml

from riscv_tools.memory_map import evaluate
from riscv_tools.new_project.layout import (
    flash_banks,
    reserved_bases,
    size_text,
)
from riscv_tools.new_project.spec import SECTOR_BYTES, ProjectSpec
from riscv_tools.new_project.template import CREATED_MARK

BOOT_REGION = "BOOT_MEMORY"
_RESERVED = ("stdout", "tohost", "fromhost")


def _replace(
    text: str, pattern: str, edit: Callable[[re.Match[str]], str]
) -> str:
    """Apply an edit to the one line a pattern finds.

    Parameters
    ----------
    text : str
        The file.
    pattern : str
        A regular expression; it is matched per line.
    edit : Callable
        Builds the new text of the match.

    Returns
    -------
    str
        The file with the line changed.

    Raises
    ------
    ValueError
        If the pattern finds no line.
    """
    new, count = re.subn(pattern, edit, text, count=1, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"platform.yaml has no line like {pattern!r}")
    return new


def _region_names(platform: dict[str, Any]) -> tuple[str, str]:
    """Name the ROM and the RAM region of the template.

    Parameters
    ----------
    platform : dict of {str: Any}
        The template, parsed.

    Returns
    -------
    tuple of (str, str)
        The ROM region (the one after the BOOT_MEMORY) and the RAM.

    Raises
    ------
    ValueError
        If the template has no such regions.
    """
    regions = cast(list[dict[str, Any]], platform.get("regions", []))
    roms = [
        r["name"]
        for r in regions
        if r.get("kind", "rom") == "rom" and r["name"] != BOOT_REGION
    ]
    rams = [r["name"] for r in regions if r.get("kind") == "ram"]
    if len(roms) != 1 or len(rams) != 1:
        raise ValueError("the template needs one ROM and one RAM region")
    return roms[0], rams[0]


def _base_of(platform: dict[str, Any], name: str) -> int:
    """Read the base address of a region.

    Parameters
    ----------
    platform : dict of {str: Any}
        The template, parsed.
    name : str
        Name of the region.

    Returns
    -------
    int
        The base address.
    """
    for region in platform["regions"]:
        if region["name"] == name:
            return int(evaluate(region["base"]))
    raise ValueError(f"the template has no region {name}")


def _set_region_size(text: str, name: str, size: int) -> str:
    """Change the size written on the line of a region.

    Parameters
    ----------
    text : str
        The file.
    name : str
        Name of the region.
    size : int
        New size in bytes.

    Returns
    -------
    str
        The file with the region resized.
    """
    pattern = rf"^(\s*- \{{name: {name},\s*base: [^,]+, size: )[^,}}]+"
    return _replace(text, pattern, lambda m: f"{m[1]}{size_text(size)}")


def _set_reserved(text: str, bases: dict[str, int]) -> str:
    """Move the `stdout`, `tohost` and `fromhost` words.

    Parameters
    ----------
    text : str
        The file.
    bases : dict of {str: int}
        The new base of each word.

    Returns
    -------
    str
        The file with the three words moved.
    """
    for word in _RESERVED:
        text = _replace(
            text,
            rf"^(\s+{word}:\s+\{{base: )0x[0-9A-Fa-f]+",
            lambda m, word=word: f"{m[1]}0x{bases[word]:08X}",
        )
    return text


def _set_banks(
    text: str, platform: dict[str, Any], rom: str, size: int
) -> str:
    """Re-split the FLASH banks for a new FLASH size.

    Parameters
    ----------
    text : str
        The file.
    platform : dict of {str: Any}
        The template, parsed.
    rom : str
        Name of the ROM region.
    size : int
        New size of the ROM in bytes.

    Returns
    -------
    str
        The file with the banks moved; unchanged when the template has
        no `flash` section.
    """
    if "flash" not in platform:
        return text
    memory = cast(dict[str, Any], platform.get("memory", {}))
    sector = int(memory.get("rom", {}).get("sector_bytes", SECTOR_BYTES))
    for bank in flash_banks(_base_of(platform, rom), size, sector):
        text = _replace(
            text,
            rf"^(\s*- \{{name: {bank.name},\s*base: )0x[0-9A-Fa-f]+"
            r"(, size: )[^}]+",
            lambda m, bank=bank: (
                f"{m[1]}0x{bank.base:08X}{m[2]}{size_text(bank.size)}"
            ),
        )
    return text


def _set_cache(text: str, name: str, bits: int) -> str:
    """Turn a cache on with a size, or off.

    Parameters
    ----------
    text : str
        The file.
    name : str
        `icache` or `dcache`.
    bits : int
        Size in bits; 0 turns the cache off.

    Returns
    -------
    str
        The file with the cache line changed.
    """
    value = f"enabled: true, size_bits: {bits}" if bits else "enabled: false"
    return _replace(
        text,
        rf"^(\s*{name}: \{{)[^}}]*",
        lambda m: f"{m[1]}{value}",
    )


def rewrite_platform(
    text: str, spec: ProjectSpec, template: str, top: str
) -> str:
    """Write the new platform's file from the template's.

    Parameters
    ----------
    text : str
        The template's `platform.yaml`.
    spec : ProjectSpec
        The choices of the project.
    template : str
        Name of the template platform, for the header.
    top : str
        The `top` component of the new platform.

    Returns
    -------
    str
        The new file.
    """
    platform = cast(dict[str, Any], yaml.safe_load(text))
    rom, ram = _region_names(platform)
    text = _replace(text, r"^(platform: ).*$", lambda m: f"{m[1]}{spec.name}")
    text = _replace(text, r"^(top: ).*$", lambda m: f"{m[1]}{top}")
    if spec.profile is not None:
        text = _replace(
            text, r"^(profile: ).*$", lambda m: f"{m[1]}{spec.profile}"
        )
    if spec.rom_bytes is not None:
        text = _set_region_size(text, rom, spec.rom_bytes)
        text = _set_banks(text, platform, rom, spec.rom_bytes)
    if spec.ram_bytes is not None:
        text = _set_region_size(text, ram, spec.ram_bytes)
        text = _set_reserved(
            text, reserved_bases(_base_of(platform, ram), spec.ram_bytes)
        )
    if spec.icache_bits is not None:
        text = _set_cache(text, "icache", spec.icache_bits)
    if spec.dcache_bits is not None:
        text = _set_cache(text, "dcache", spec.dcache_bits)
    header = (
        f"# Platform {spec.display} ({spec.name}), {CREATED_MARK} "
        f"from {template}.\n"
        "# Edit this file and run `riscv-tools generate-memory-map` again.\n"
    )
    return header + text
