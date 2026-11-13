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
from riscv_tools.memory_map.core_profile import EXTRAS, legacy_to_core
from riscv_tools.new_project.layout import (
    flash_banks,
    reserved_bases,
    size_text,
)
from riscv_tools.new_project.spec import SECTOR_BYTES, ProjectSpec
from riscv_tools.new_project.template import CREATED_MARK

_RESERVED = ("stdout", "tohost", "fromhost")


def _core_text(profile: str, extras: list[str]) -> str:
    """Write the `core` block of a profile.

    Parameters
    ----------
    profile : str
        The name of the profile.
    extras : list of str
        The extras of the template, which the new profile keeps.

    Returns
    -------
    str
        The block, `core:` and its three keys, ending in a line break.
    """
    core = legacy_to_core(profile, extras)
    listed = "".join(f"    - {name}\n" for name in core["extensions"])
    return (
        f"core:\n  type: {core['type']}\n  base: {core['base']}\n"
        f"  extensions:{'\n' + listed if listed else ' []\n'}"
    )


def _set_core(text: str, platform: dict[str, Any], profile: str) -> str:
    """Replace the `core` block of the template by the one of a profile.

    Parameters
    ----------
    text : str
        The file.
    platform : dict of {str: Any}
        The template platform, parsed.
    profile : str
        The name of the new profile.

    Returns
    -------
    str
        The file with the block replaced; the extras of the template
        (Zihintntl, Interrupts and the like) stay in it.

    Raises
    ------
    ValueError
        If the template has no `core` block.
    """
    block = cast("dict[str, Any]", platform.get("core") or {})
    kept = [
        str(name)
        for name in cast("list[Any]", block.get("extensions") or [])
        if str(name).lower() in {e.lower() for e in EXTRAS}
    ]
    new, count = re.subn(
        r"^core:[^\n]*\n(?:[ \t][^\n]*\n)*",
        lambda _: _core_text(profile, kept),
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("the template platform has no `core` block")
    return new


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


def _segment_of(platform: dict[str, Any], side: str) -> dict[str, Any]:
    """Read the segment of `instructions` or `data` of the template.

    Parameters
    ----------
    platform : dict of {str: Any}
        The template, parsed.
    side : str
        `instructions` or `data`.

    Returns
    -------
    dict of {str: Any}
        The one segment of the side.

    Raises
    ------
    ValueError
        If the template has no segment on the side.
    """
    memory = cast(dict[str, Any], platform.get("memory") or {})
    items = cast(list[dict[str, Any]], memory.get(side) or [])
    if len(items) != 1:
        raise ValueError(f"the template needs one segment in memory.{side}")
    return items[0]


def _base_of(platform: dict[str, Any], side: str) -> int:
    """Read the base address of a side.

    Parameters
    ----------
    platform : dict of {str: Any}
        The template, parsed.
    side : str
        `instructions` or `data`.

    Returns
    -------
    int
        The base address.
    """
    return int(evaluate(_segment_of(platform, side)["base"]))


def _edit_side(text: str, side: str, edit: Callable[[str], str]) -> str:
    """Edit the text of the segment of one side of `memory`.

    Parameters
    ----------
    text : str
        The file.
    side : str
        `instructions` or `data`.
    edit : Callable
        Builds the new text of the segment (its lines, indented below
        `<side>:`).

    Returns
    -------
    str
        The file with the segment changed.

    Raises
    ------
    ValueError
        If the file has no such side.
    """
    pattern = rf"^(  {side}:\n)((?:    [^\n]*\n|[ \t]*\n)*)"
    found = re.search(pattern, text, flags=re.MULTILINE)
    if found is None:
        raise ValueError(f"platform.yaml has no `{side}:` block in memory")
    return text[: found.start(2)] + edit(found[2]) + text[found.end(2) :]


def _set_region_size(text: str, side: str, size: int) -> str:
    """Change the size written in the segment of a side.

    Parameters
    ----------
    text : str
        The file.
    side : str
        `instructions` or `data`.
    size : int
        New size in bytes.

    Returns
    -------
    str
        The file with the segment resized.
    """

    def edit(block: str) -> str:
        new, count = re.subn(
            r"^(      size: )[^\n#]*",
            lambda m: f"{m[1]}{size_text(size)}",
            block,
            count=1,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise ValueError(f"memory.{side} has no `size:` line")
        return new

    return _edit_side(text, side, edit)


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
            rf"^(  {word}:\n    base: )0x[0-9A-Fa-f]+",
            lambda m, word=word: f"{m[1]}0x{bases[word]:08X}",
        )
    return text


def _set_banks(text: str, platform: dict[str, Any], size: int) -> str:
    """Re-split the FLASH banks for a new FLASH size.

    Parameters
    ----------
    text : str
        The file.
    platform : dict of {str: Any}
        The template, parsed.
    size : int
        New size of the instruction segment in bytes.

    Returns
    -------
    str
        The file with the banks moved; unchanged when the template has
        no `flash` section.
    """
    if "flash" not in platform:
        return text
    segment = _segment_of(platform, "instructions")
    sector = int(segment.get("sector_bytes", SECTOR_BYTES))
    for bank in flash_banks(_base_of(platform, "instructions"), size, sector):
        text = _replace(
            text,
            rf"^(\s*- \{{name: {bank.name},\s*base: )0x[0-9A-Fa-f]+"
            r"(, size: )[^}]+",
            lambda m, bank=bank: (
                f"{m[1]}0x{bank.base:08X}{m[2]}{size_text(bank.size)}"
            ),
        )
    return text


def _set_cache(text: str, side: str, bits: int) -> str:
    """Turn the cache of a side on with a size, or off.

    Parameters
    ----------
    text : str
        The file.
    side : str
        `instructions` or `data`.
    bits : int
        Size in bits; 0 turns the cache off.

    Returns
    -------
    str
        The file with the `cache` block of the segment changed.
    """

    def edit(block: str) -> str:
        bare = re.sub(
            r"^      cache:\n(?:        [^\n]*\n)*", "", block, flags=re.M
        )
        if not bits:
            return bare
        cache = f"      cache:\n        size_bits: {bits}\n"
        new, count = re.subn(
            r"^(      on_bus: [^\n]*\n)",
            lambda m: m[1] + cache,
            bare,
            count=1,
            flags=re.MULTILINE,
        )
        return new if count else bare + cache

    return _edit_side(text, side, edit)


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
    text = _replace(text, r"^(platform: ).*$", lambda m: f"{m[1]}{spec.name}")
    text = _replace(text, r"^(top: ).*$", lambda m: f"{m[1]}{top}")
    if spec.profile is not None:
        text = _set_core(text, platform, spec.profile)
    if spec.rom_bytes is not None:
        text = _set_region_size(text, "instructions", spec.rom_bytes)
        text = _set_banks(text, platform, spec.rom_bytes)
    if spec.ram_bytes is not None:
        text = _set_region_size(text, "data", spec.ram_bytes)
        text = _set_reserved(
            text, reserved_bases(_base_of(platform, "data"), spec.ram_bytes)
        )
    if spec.icache_bits is not None:
        text = _set_cache(text, "instructions", spec.icache_bits)
    if spec.dcache_bits is not None:
        text = _set_cache(text, "data", spec.dcache_bits)
    header = (
        f"# Platform {spec.name}, {CREATED_MARK} from {template}.\n"
        "# Edit this file and run `riscv-tools generate-memory-map` again.\n"
    )
    return header + text
