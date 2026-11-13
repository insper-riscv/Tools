"""Tests for the memory block and the old keys it replaces."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check_equal, check_in

from riscv_tools.memory_map import load_platform, validate_platform

MEMORY: dict[str, Any] = {
    "boot": {"base": 0, "size": "4K"},
    "instructions": [
        {
            "type": "emulated",
            "base": 0x1000,
            "size": "252K",
            "on_bus": True,
            "latency": {"first": 24, "next": 4},
            "sector_bytes": 4096,
            "cache": {"size_bits": 32768},
        }
    ],
    "data": [
        {"type": "sdram", "base": 0x40000000, "size": "64M", "on_bus": True}
    ],
}


def _load(root: Path, **changes: Any) -> dict[str, Any]:
    """Write a platform with the memory block and load it."""
    reserved = {"fromhost": {"base": 0x43FFFFF0, "size": 8}}
    data = {"memory": MEMORY, "reserved": reserved} | changes
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return load_platform(path)


def test_the_block_gives_the_regions_and_the_four_choices(
    tmp_path: Path,
) -> None:
    """Names and kinds are fixed; the choice is `type` and `on_bus`."""
    platform = _load(tmp_path)
    check_equal(
        [(r["name"], r.get("exec", False)) for r in platform["regions"]],
        [("BOOT_MEMORY", True), ("FLASH", True), ("RAM", False)],
    )
    memory = platform["memory"]
    check_equal(
        memory["rom"],
        {
            "external": True,
            "backend": "emulado",
            "latency": {"first": 24, "next": 4},
            "sector_bytes": 4096,
        },
    )
    check_equal(
        memory["ram"],
        {"external": True, "backend": "dispositivo", "device": "sdram"},
    )
    check_equal(memory["icache"], {"enabled": True, "size_bits": 32768})
    check_equal(memory["dcache"], {"enabled": False})
    check_equal([str(p) for p in validate_platform(platform)], [])


def test_two_segments_are_refused_in_this_phase(tmp_path: Path) -> None:
    """The second segment waits for the tables of ranges."""
    memory = dict(MEMORY)
    memory["data"] = [
        *MEMORY["data"],
        dict(MEMORY["data"][0], base=0x50000000),
    ]
    with pytest.raises(ValueError, match="vários segmentos ainda não") as e:
        _load(tmp_path, memory=memory)
    check_in("memory.data", str(e.value))


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("regions", "regions is no longer accepted"),
        ("memory", "memory.rom is no longer accepted"),
    ],
)
def test_the_old_keys_are_refused(tmp_path: Path, key: str, text: str) -> None:
    """`regions` and the four choices say how to migrate."""
    value: Any = (
        [{"name": "BOOT_MEMORY", "base": 0, "size": "4K", "kind": "rom"}]
        if key == "regions"
        else {"rom": {"external": True}}
    )
    with pytest.raises(ValueError, match=text):
        _load(tmp_path, **{key: value})


@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"type": "tape"}, "must be one of"),
        ({"kind": "rom"}, "no longer exists"),
        ({"exec": True}, "no longer exists"),
        ({"on_bus": False}, "needs on_bus: true"),
        ({"other": 1}, "unknown keys"),
    ],
)
def test_a_bad_segment_is_refused(
    tmp_path: Path, change: dict[str, Any], text: str
) -> None:
    """Each mistake in a segment has its own message."""
    memory = dict(MEMORY)
    memory["data"] = [dict(MEMORY["data"][0], **change)]
    with pytest.raises(ValueError, match=text):
        _load(tmp_path, memory=memory)


def test_boot_takes_only_base_and_size(tmp_path: Path) -> None:
    """`kind` and `exec` of the old BOOT_MEMORY are gone."""
    memory = dict(MEMORY, boot={"base": 0, "size": "4K", "exec": True})
    with pytest.raises(ValueError, match="no longer exists"):
        _load(tmp_path, memory=memory)


def test_on_bus_comes_in_both_segments_or_in_none(tmp_path: Path) -> None:
    """Without it the choice is left to `--memory`."""
    data = dict(MEMORY["data"][0])
    del data["on_bus"]
    data["type"] = "onchip"
    inst = {"type": "onchip", "base": 0x1000, "size": "252K"}
    memory = dict(MEMORY, instructions=[inst], data=[data])
    check_in("regions", _load(tmp_path, memory=memory))
    check_equal("memory" in _load(tmp_path, memory=memory), False)
    half = dict(MEMORY, instructions=[inst])
    with pytest.raises(ValueError, match="both segments or in none"):
        _load(tmp_path, memory=half)
