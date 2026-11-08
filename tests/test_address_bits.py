"""Tests for `address_bits`, the window and the rv64 profiles."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check,
    check_equal,
    check_in,
    profile_matrix,
)

from riscv_tools.memory_map import (
    config_from_platform,
    resolve,
    set_override,
    validate_platform,
)

MATRIX = profile_matrix("rv32i", "rv64e", "rv64i")

PLATFORM: dict[str, Any] = {
    "profile": "rv32im",
    "profiles": "matrix.yaml",
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "peripherals": [{"name": "UART", "base": "0xC0000000", "id": 4}],
    "config": {"rom": "FLASH", "ram": "RAM", "addr_widths": ["rom"]},
}
GENERICS = {"has_access_faults": True}


def _with(**changes: Any) -> dict[str, Any]:
    """Copy the 32-bit platform with some fields changed."""
    return {**PLATFORM, **changes}


def _small(**changes: Any) -> dict[str, Any]:
    """Copy the platform with the 24-bit map (window at 0x800000)."""
    return _with(
        **{
            "address_bits": 24,
            "peripherals": [{"name": "UART", "base": "0xC00000", "id": 4}],
            **changes,
        }
    )


def _wide(**changes: Any) -> dict[str, Any]:
    """Copy the platform with an rv64 profile and a 40-bit map."""
    return _with(
        **{
            "profile": "rv64im",
            "address_bits": 40,
            "peripherals": [{"name": "UART", "base": "0xC000000000", "id": 4}],
            **changes,
        }
    )


def _problems(platform: dict[str, Any], **kwargs: Any) -> list[str]:
    """List the problems of the platform as text."""
    return [str(p) for p in validate_platform(platform, **kwargs)]


def _write(root: Path, platform: dict[str, Any]) -> Path:
    """Write the platform and its matrix."""
    (root / "matrix.yaml").write_text(yaml.safe_dump(MATRIX))
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    return path


def test_the_32_bit_platform_is_consistent_without_the_field() -> None:
    """A platform without `address_bits` is the 32-bit one of today."""
    check_equal(_problems(PLATFORM), [])
    check_equal(_problems(_with(address_bits=32)), [])


def test_the_narrow_and_wide_platforms_are_consistent() -> None:
    """24 bits (rv32) and 40 bits (rv64) pass every V-A check."""
    check_equal(_problems(_small(), generics=GENERICS), [])
    check_equal(_problems(_wide(), generics=GENERICS), [])


@pytest.mark.parametrize("value", [8, 15, 65, "32", 32.0, True, None])
def test_v_a1_address_bits_is_an_integer_from_16_to_64(value: Any) -> None:
    """V-A1: the field is an integer from 16 to 64."""
    problems = _problems(_with(address_bits=value))
    check(any("V-A1 address_bits" in p for p in problems), str(problems))


def test_v_a2_above_32_bits_needs_an_rv64_profile() -> None:
    """V-A2: 33 bits or more with an rv32 profile is refused."""
    problems = _problems(_with(address_bits=40))
    check(any("V-A2 address_bits 40" in p for p in problems), str(problems))
    check_equal([p for p in _problems(_wide()) if "V-A2" in p], [])


def test_v_a3_a_region_must_fit_the_space() -> None:
    """V-A3: a region that ends beyond `2**address_bits` is refused."""
    problems = _problems(
        _small(
            regions=[
                *MAP_REGIONS[:2],
                {
                    "name": "RAM",
                    "base": "0xF00000",
                    "size": "2M",
                    "kind": "ram",
                },
            ]
        )
    )
    check(any("V-A3 region RAM" in p for p in problems), str(problems))


def test_v_a4_the_window_and_the_ids_follow_the_width() -> None:
    """V-A4: a region above the window or a base off the id fails."""
    high = _small(
        regions=[
            *MAP_REGIONS[:2],
            {"name": "RAM", "base": "0x700000", "size": "2M", "kind": "ram"},
        ]
    )
    check(
        any(
            "not below the peripheral window 0x800000" in p
            for p in _problems(high)
        ),
        str(_problems(high)),
    )
    off = _small(peripherals=[{"name": "UART", "base": "0xC0000000", "id": 4}])
    check(
        any(
            "peripheral UART base is not 0xC00000" in p for p in _problems(off)
        ),
        str(_problems(off)),
    )
    far = _with(peripherals=[{"name": "X", "base": "0x0", "id": 16}])
    check(
        any("V-A4 peripheral X id 16" in p for p in _problems(far)),
        str(_problems(far)),
    )


def test_v_a4_a_fixed_window_replaces_the_derived_one() -> None:
    """`periph_window` fixes the base the peripherals are or-ed into."""
    fixed = _with(
        periph_window="0xA0000000",
        peripherals=[{"name": "UART", "base": "0xB0000000", "id": 1}],
    )
    check_equal(_problems(fixed), [])


def test_v_a5_a_narrow_address_needs_the_access_faults() -> None:
    """V-A5: a width below `xlen` needs the access faults."""
    problems = _problems(_small(), generics={"has_access_faults": False})
    check(any("V-A5 address_bits 24" in p for p in problems), str(problems))
    check_equal(_problems(_small()), [])
    wide32 = _problems(
        _wide(
            address_bits=32,
            peripherals=[{"name": "UART", "base": "0xC0000000", "id": 4}],
        ),
        generics={},
    )
    check(any("V-A5" in p and "xlen 64" in p for p in wide32), str(wide32))


@pytest.mark.parametrize("key", ["entry", "wait_restart"])
def test_v_a6_the_boot_addresses_must_be_in_the_space(key: str) -> None:
    """V-A6: a boot address at or above `2**address_bits` is refused."""
    problems = _problems(_small(boot={**PLATFORM["boot"], key: "0x1000000"}))
    check(any(f"V-A6 boot.{key}" in p for p in problems), str(problems))


def test_resolve_accepts_the_rv64_profiles(tmp_path: Path) -> None:
    """The base letter and `xlen` come off the name prefix."""
    for name, base, xlen in (
        ("rv32i", "i", 32),
        ("rv64i", "i", 64),
        ("rv64em", "e", 64),
    ):
        path = _write(tmp_path, _with(profile=name))
        platform = yaml.safe_load(path.read_text())
        got = resolve(platform, path)
        check_equal((got[0], got[2]), (base, xlen), name)
    check_in(
        "has_m",
        resolve(
            yaml.safe_load(
                _write(tmp_path, _with(profile="rv64im")).read_text()
            ),
            tmp_path / "platform.yaml",
        )[1],
    )


def test_resolve_rejects_a_name_without_a_valid_base(tmp_path: Path) -> None:
    """Only `rv32i`, `rv32e`, `rv64i` and `rv64e` start a profile."""
    for name in ("rv128i", "rv64x", "rv6", "arm"):
        platform = {k: v for k, v in PLATFORM.items() if k != "profiles"}
        path = _write(tmp_path, {**platform, "profile": name})
        with pytest.raises(ValueError, match="rv64e"):
            resolve(yaml.safe_load(path.read_text()), path)


def test_the_override_can_pick_an_rv64_profile(tmp_path: Path) -> None:
    """`--profile rv64im` replaces the profile of the platform."""
    path = _write(tmp_path, PLATFORM)
    set_override("rv64im")
    check_equal(resolve(yaml.safe_load(path.read_text()), path)[2], 64)


def test_the_config_gets_the_new_keys_only_off_the_default(
    tmp_path: Path,
) -> None:
    """`addr_bits` and `xlen` appear in the config only when not 32."""
    plain = config_from_platform(_write(tmp_path, PLATFORM))
    check_equal("addr_bits" in plain["memory"], False)
    check_equal("xlen" in plain["isa"], False)
    wide = config_from_platform(_write(tmp_path, _wide()))
    check_equal(wide["memory"]["addr_bits"], 40)
    check_equal(wide["isa"], {"base": "i", "xlen": 64})
