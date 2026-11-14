"""Tests for the `memory` section and the `--memory` option."""

import itertools
import re
import sys
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from support import (
    MAP_REGIONS,
    MAP_RESERVED,
    check,
    check_equal,
    check_in,
    check_is,
    check_not_in,
    dump_platform,
)

from riscv_tools import cli
from riscv_tools.memory_map import (
    config_from_platform,
    memory_notes,
    render_all,
    set_memory_override,
    validate_platform,
)

MEMORY: dict[str, Any] = {
    "rom": {"external": True},
    "ram": {"external": True},
    "icache": {"enabled": True, "size_bits": 4096},
    "dcache": {"enabled": True, "size_bits": 1024},
}
PLATFORM: dict[str, Any] = {
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "config": {"rom": "FLASH", "ram": "RAM"},
    "memory": MEMORY,
    "generate": {
        "vhdl": {
            "package": "map_pkg",
            "path": "out/map_pkg.vhd",
            "ram": "RAM",
            "rom": "FLASH",
        },
    },
}
PACKAGE = "out/map_pkg.vhd"


@pytest.fixture(autouse=True)
def _no_override() -> Iterator[None]:
    """Start each test with the memory of the platform."""
    set_memory_override(None)
    yield
    set_memory_override(None)


def _platform(**changes: Any) -> dict[str, Any]:
    """Copy the platform and replace top-level sections.

    Parameters
    ----------
    **changes : Any
        Sections to replace; None removes the section.

    Returns
    -------
    dict of {str: Any}
        The platform.
    """
    platform = deepcopy(PLATFORM)
    for key, value in changes.items():
        if value is None:
            platform.pop(key, None)
        else:
            platform[key] = value
    return platform


def _render(root: Path, platform: dict[str, Any]) -> str:
    """Write the platform and render its VHDL package.

    Parameters
    ----------
    root : Path
        The project root.
    platform : dict of {str: Any}
        The platform.

    Returns
    -------
    str
        The package.
    """
    path = root / "platform.yaml"
    path.write_text(dump_platform(platform))
    return render_all(path, root)[root / PACKAGE]


def _choice(rom: str, ram: str, icache: str, dcache: str) -> str:
    """Spell a combination as the value of `--memory`.

    Parameters
    ----------
    rom : str
        `int` or `ext`.
    ram : str
        `int` or `ext`.
    icache : str
        `on` or `off`.
    dcache : str
        `on` or `off`.

    Returns
    -------
    str
        The comma list.
    """
    return f"rom={rom},ram={ram},icache={icache},dcache={dcache}"


def test_the_memory_section_writes_the_constants(tmp_path: Path) -> None:
    """The package has the choice, the sizes and the port flags."""
    text = _render(tmp_path, _platform())
    check_in("constant FLASH_ON_BUS        : boolean  := true;", text)
    check_in("constant RAM_ON_BUS          : boolean  := true;", text)
    check_in("constant HAS_ICACHE          : boolean  := true;", text)
    check_in("constant HAS_DCACHE          : boolean  := true;", text)
    check_in("constant ICACHE_SIZE_BITS    : positive := 4096;", text)
    check_in("constant DCACHE_SIZE_BITS    : positive := 1024;", text)
    check_not_in("VIA_PORT", text)
    check_not_in(" CACHE_WINDOW_BITS ", text)


def test_a_platform_without_memory_keeps_the_old_package(
    tmp_path: Path,
) -> None:
    """Without `memory` none of the new constants appears."""
    text = _render(tmp_path, _platform(memory=None))
    for name in ("HAS_ICACHE", "SIZE_BITS", "VIA_PORT", "ON_BUS"):
        check_not_in(name, text)


def test_nine_of_the_sixteen_combinations_are_valid(
    tmp_path: Path,
) -> None:
    """The caches need their memory on the bus: seven are refused."""
    packages: set[str] = set()
    refused = 0
    for rom, ram, icache, dcache in itertools.product(
        ("int", "ext"), ("int", "ext"), ("on", "off"), ("on", "off")
    ):
        set_memory_override(_choice(rom, ram, icache, dcache))
        if (icache == "on" and rom == "int") or (
            dcache == "on" and ram == "int"
        ):
            with pytest.raises(ValueError, match=r"V-C[12]"):
                _render(tmp_path, _platform())
            refused += 1
            continue
        text = _render(tmp_path, _platform())
        packages.add(text)
        check_in(f"{str(rom == 'ext').lower()};", text)
        flag = str(dcache == "on").lower()
        check_in(f"HAS_DCACHE          : boolean  := {flag};", text)
    check_equal((len(packages), refused), (9, 7))


def test_off_caches_have_the_minimum_size(tmp_path: Path) -> None:
    """A cache that is off writes 256 bits."""
    set_memory_override(_choice("int", "int", "off", "off"))
    text = _render(tmp_path, _platform())
    check_in("ICACHE_SIZE_BITS    : positive := 256;", text)
    check_in("DCACHE_SIZE_BITS    : positive := 256;", text)


def test_the_override_without_a_section_needs_the_four_keys(
    tmp_path: Path,
) -> None:
    """A platform with no `memory` takes the choice from `--memory`."""
    set_memory_override(_choice("ext", "int", "on", "off"))
    text = _render(tmp_path, _platform(memory=None))
    check_in("FLASH_ON_BUS        : boolean  := true;", text)
    check_in("ICACHE_SIZE_BITS    : positive := 4096;", text)
    set_memory_override("rom=ext")
    with pytest.raises(ValueError, match=r"memory\.ram\.external"):
        _render(tmp_path, _platform(memory=None))


def test_a_size_in_the_override_turns_the_cache_on(tmp_path: Path) -> None:
    """`icache=512` is an enabled cache of 512 bits."""
    set_memory_override("icache=512,dcache=off")
    text = _render(tmp_path, _platform())
    check_in("ICACHE_SIZE_BITS    : positive := 512;", text)
    check_in("HAS_DCACHE          : boolean  := false;", text)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("rom", "not key=value"),
        ("flash=ext", "unknown key"),
        ("rom=ext,rom=int", "given twice"),
        ("rom=maybe", "use int or ext"),
        ("icache=maybe", "use on, off or a size"),
    ],
)
def test_a_malformed_override_is_rejected(text: str, message: str) -> None:
    """The message names the pair that is wrong."""
    with pytest.raises(ValueError, match=message):
        set_memory_override(text)


def test_the_flag_reaches_the_generated_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--memory` of the command line picks the combination."""
    (tmp_path / "platform.yaml").write_text(dump_platform(PLATFORM))
    argv = ["riscv-tools", "--root", str(tmp_path)]
    argv += ["--memory", _choice("int", "int", "off", "off")]
    argv += ["generate-memory-map", "--platform", "platform.yaml"]
    monkeypatch.setattr(sys, "argv", argv)
    try:
        cli.main()
    finally:
        set_memory_override(None)
    text = (tmp_path / PACKAGE).read_text()
    check_in("FLASH_ON_BUS        : boolean  := false;", text)


def test_a_bad_flag_stops_the_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed `--memory` is an argument error."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["riscv-tools", "--memory", "rom=x", "profiles", "--spec", "s"],
    )
    with pytest.raises(SystemExit) as stop:
        cli.main()
    check_equal(stop.value.code, 2)
    check_in("rom='x' is not valid", capsys.readouterr().err)


def _bad(section: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """Replace entries of the memory section of the platform.

    Parameters
    ----------
    section : dict of {str: Any}
        Entries of `memory`; None removes the entry.
    **changes : Any
        Top-level sections to replace.

    Returns
    -------
    dict of {str: Any}
        The platform.
    """
    memory = deepcopy(MEMORY)
    for key, value in section.items():
        if value is None:
            memory.pop(key, None)
        else:
            memory[key] = value
    return _platform(memory=memory, **changes)


@pytest.mark.parametrize(
    ("platform", "message"),
    [
        (_bad({"rom": None}), r"memory\.rom\.external is required"),
        (_bad({"dcache": {}}), r"memory\.dcache\.enabled is required"),
        (_bad({"ram": {"external": "yes"}}), r"memory\.ram\.external"),
        (_bad({"flash": {}}), r"memory\.flash is not a memory choice"),
        (_bad({"rom": {"external": True, "x": 1}}), r"memory\.rom\.x"),
        (
            _bad({"icache": {"enabled": True}}),
            r"icache\.size_bits is required when enabled",
        ),
        (
            _bad({"icache": {"enabled": True, "size_bits": 3000}}),
            r"icache\.size_bits \(3000\) must be a power of two",
        ),
        (
            _bad({"dcache": {"enabled": True, "size_bits": 128}}),
            r"dcache\.size_bits \(128\)",
        ),
        (
            _bad({"icache": {"enabled": False, "size_bits": 100}}),
            r"icache\.size_bits \(100\)",
        ),
    ],
)
def test_a_malformed_section_is_rejected(
    platform: dict[str, Any], message: str
) -> None:
    """V1 and V2 fail with the field that is wrong."""
    problems = [str(p) for p in validate_platform(platform)]
    check(any(re.search(message, p) for p in problems), str(problems))


def test_memory_must_be_a_mapping() -> None:
    """A list under `memory` is rejected."""
    problems = [str(p) for p in validate_platform(_platform(memory=[1]))]
    check(any("must be a mapping" in p for p in problems), str(problems))


def test_the_old_external_flags_cannot_sit_beside_memory(
    tmp_path: Path,
) -> None:
    """`rom_external` in `generate.vhdl` and `memory` are exclusive."""
    platform = _platform()
    platform["generate"]["vhdl"]["rom_external"] = True
    with pytest.raises(ValueError, match=r"generate\.vhdl\.rom_external"):
        _render(tmp_path, platform)


def _big_ram(base: str, size: str, fromhost: str) -> dict[str, Any]:
    """Build a platform whose RAM is placed at base with the given size.

    Parameters
    ----------
    base : str
        The base of the RAM.
    size : str
        The size of the RAM.
    fromhost : str
        The address of the host word, inside the RAM.

    Returns
    -------
    dict of {str: Any}
        The platform.
    """
    regions = deepcopy(MAP_REGIONS)
    regions[2] |= {"base": base, "size": size}
    return _platform(
        regions=regions, reserved={"fromhost": {"base": fromhost, "size": "8"}}
    )


def test_a_region_across_the_last_window_is_rejected(tmp_path: Path) -> None:
    """V3: no window up to 512 MiB holds a region across its edge."""
    platform = _big_ram("0x1FFF0000", "128K", "0x1FFFFFF0")
    with pytest.raises(ValueError, match="512 MiB window"):
        _render(tmp_path, platform)
    set_memory_override(_choice("int", "int", "off", "off"))
    _render(tmp_path, platform)


def test_the_window_widens_to_hold_the_ram(tmp_path: Path) -> None:
    """V3: a 128 MiB RAM makes the window of the cache tag 128 MiB."""
    platform = _big_ram("0x40000000", "128M", "0x47FFFFF0")
    check_in(
        "I_CACHE_WINDOW_BITS : natural  := 27;", _render(tmp_path, platform)
    )
    check_in(
        "D_CACHE_WINDOW_BITS : natural  := 26;", _render(tmp_path, _platform())
    )


def test_a_region_that_crosses_64_mib_fits_a_wider_window(
    tmp_path: Path,
) -> None:
    """V3: 0x3FF0000 to 0x4010000 sits in one 128 MiB window."""
    platform = _big_ram("0x3FF0000", "128K", "0x400FFF0")
    check_in(
        "I_CACHE_WINDOW_BITS : natural  := 27;", _render(tmp_path, platform)
    )


def test_the_simulation_gets_the_window_only_when_it_is_wide(
    tmp_path: Path,
) -> None:
    """The parameters carry CACHE_WINDOW_BITS above the default only."""
    path = tmp_path / "platform.yaml"
    path.write_text(dump_platform(_platform()))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_not_in("CACHE_WINDOW_BITS", parameters)
    wide = _big_ram("0x40000000", "128M", "0x47FFFFF0")
    path.write_text(dump_platform(wide))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_equal(parameters["CACHE_WINDOW_BITS"], "27")


def test_the_rom_must_fit_the_router_window(tmp_path: Path) -> None:
    """V4: the region router sees 1024 KiB of ROM."""
    regions = deepcopy(MAP_REGIONS)
    regions[1] |= {"size": "2M"}
    regions[2] |= {"base": "0x300000"}
    reserved = {"fromhost": {"base": "0x327FF0", "size": "8"}}
    platform = _platform(regions=regions, reserved=reserved)
    with pytest.raises(ValueError, match="window of the region router"):
        _render(tmp_path, platform)
    set_memory_override(_choice("int", "int", "off", "off"))
    _render(tmp_path, platform)


def _big_rom(device: str) -> dict[str, Any]:
    """Build a platform whose ROM is 2 MiB of the given device.

    Parameters
    ----------
    device : str
        The `memory.rom.device`.

    Returns
    -------
    dict of {str: Any}
        The platform.
    """
    regions = deepcopy(MAP_REGIONS)
    regions[1] |= {"size": "2M"}
    regions[2] |= {"base": "0x300000"}
    reserved = {"fromhost": {"base": "0x327FF0", "size": "8"}}
    memory = deepcopy(MEMORY)
    memory["rom"] = {
        "external": True,
        "backend": "dispositivo",
        "device": device,
    }
    return _platform(regions=regions, reserved=reserved, memory=memory)


def test_a_chip_rom_keeps_the_router_window(tmp_path: Path) -> None:
    """V4: a NOR chip is held to the 1024 KiB the router sees."""
    with pytest.raises(ValueError, match="window of the region router"):
        _render(tmp_path, _big_rom("nor"))


def test_an_sdram_rom_is_not_held_to_the_router_window(
    tmp_path: Path,
) -> None:
    """V4: the SDRAM is read as the RAM is, with no 1024 KiB window."""
    text = _render(tmp_path, _big_rom("sdram"))
    check_in("FLASH", text)


def test_a_cache_needs_the_bypassed_host_words(tmp_path: Path) -> None:
    """V10: the host words sit in the page the cache skips."""
    with pytest.raises(ValueError, match=r"needs reserved\.fromhost"):
        _render(tmp_path, _platform(reserved={}))
    moved = {"fromhost": {"base": "0x9000", "size": "8"}}
    with pytest.raises(ValueError, match="last 4 KiB page"):
        _render(tmp_path, _platform(reserved=moved))
    set_memory_override(_choice("ext", "ext", "off", "off"))
    _render(tmp_path, _platform(reserved={}))


def test_notes_say_what_is_not_an_error() -> None:
    """The path of the peripherals is a remark, not an error."""
    set_memory_override(_choice("ext", "ext", "on", "on"))
    notes = memory_notes(_platform(peripherals=[{"name": "U"}]))
    check_equal(len(notes), 1)
    check_in("peripherals", notes[0])
    check_equal(memory_notes(_platform()), [])
    check_equal(memory_notes(_platform(memory=None)), [])


def test_the_config_carries_the_choice_and_the_widths(
    tmp_path: Path,
) -> None:
    """The simulation gets the choice; internal memories get widths."""
    path = tmp_path / "platform.yaml"
    path.write_text(dump_platform(_platform()))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_is(parameters["ROM_EXTERNAL"], True)
    check_is(parameters["HAS_ICACHE"], True)
    check_equal(parameters["DCACHE_SIZE_BITS"], "1024")
    check_in("boot_memory_addr_width", parameters)
    check_not_in("rom_addr_width", parameters)
    set_memory_override(_choice("int", "int", "off", "off"))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_in("rom_addr_width", parameters)
    check_in("ram_addr_width", parameters)
    check_is(parameters["ROM_EXTERNAL"], False)


def test_listed_widths_win_and_no_memory_adds_nothing(
    tmp_path: Path,
) -> None:
    """`config.addr_widths` is kept; no `memory` adds no parameter."""
    path = tmp_path / "platform.yaml"
    listed = _platform()
    listed["config"]["addr_widths"] = ["ram"]
    path.write_text(dump_platform(listed))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_in("ram_addr_width", parameters)
    check_not_in("boot_memory_addr_width", parameters)
    path.write_text(dump_platform(_platform(memory=None)))
    parameters = config_from_platform(path)["sim"]["parameters"]
    check_not_in("ROM_EXTERNAL", parameters)
    check_equal(
        render_all(path, tmp_path)[tmp_path / PACKAGE].count("VIA_PORT"), 0
    )


def test_the_board_fields_of_a_memory_are_known_fields() -> None:
    """The fields of the board catalog are not typos."""
    platform = {
        "regions": [
            {"name": "BOOT_MEMORY", "base": "0x0", "size": "4K"},
            {"name": "RAM", "base": "0x40000000", "size": "1M", "kind": "ram"},
        ],
        "memory": {
            "rom": {"external": False},
            "ram": {
                "external": True,
                "backend": "dispositivo",
                "device": "sdram",
            },
            "icache": {"enabled": False},
            "dcache": {"enabled": False},
        },
    }
    check_equal(
        [p for p in validate_platform(platform) if "not a field" in str(p)],
        [],
    )
