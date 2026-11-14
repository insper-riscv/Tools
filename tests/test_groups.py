"""Tests for the groups of the GPIO and of the display blocks."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import check, check_equal, check_in

from riscv_tools.memory_map import (
    load_platform,
    memory_notes,
    render_all,
    symbols,
    validate_platform,
)
from riscv_tools.memory_map.layout import to_layout

BOARDS: dict[str, dict[str, tuple[Any, str]]] = {
    "big": {
        "leds": ("LEDR[17:0]", "high"),
        "switches": ("SW[17:0]", "high"),
        "keys": ("KEY[3:0]", "low"),
        "display": ("HEX[7:0][6:0]", "low"),
    },
    "small": {
        "leds": ("LEDR[9:0]", "high"),
        "switches": ("SW[9:0]", "high"),
        "keys": ("KEY[3:0]", "low"),
        "display": ("HEX[5:0][6:0]", "low"),
    },
    "nano": {"leds": ("LED[7:0]", "high"), "keys": ("KEY[1:0]", "low")},
    "wide": {
        "gpio": (["GPIO_0[35:0]", "GPIO_1[35:0]"], "high"),
        "hsmc": (["HSMC_D[3:0]", "HSMC_RX_D_N[16:0]"], "high"),
    },
}
MEMORY = {
    "boot": {"base": 0, "size": "4K"},
    "instructions": [{"type": "onchip", "base": 0x1000, "size": "4K"}],
    "data": [{"type": "onchip", "base": 0x40000000, "size": "64K"}],
}


def _catalog(root: Path) -> None:
    """Write the `board.yaml` of the boards above."""
    (root / "boards/families").mkdir(parents=True)
    for name, roles in BOARDS.items():
        folder = root / "boards" / name
        folder.mkdir()
        io = {
            role: {"signals": signals, "active": active}
            for role, (signals, active) in roles.items()
        }
        (folder / "board.yaml").write_text(yaml.safe_dump({"io": io}))


def _write(root: Path, peripherals: dict[str, Any], **changes: Any) -> Path:
    """Write a platform with the blocks and the catalog."""
    _catalog(root)
    data = {
        "boards": ["small"],
        "memory": MEMORY,
        "peripherals": peripherals,
    } | changes
    path = root / "src/p/platform.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def _leds(groups: Any) -> dict[str, Any]:
    """Describe a block of the LEDs."""
    return {
        "LEDR": {
            "kind": "gpio",
            "role": "leds",
            "base": 0x80002000,
            "groups": groups,
        }
    }


@pytest.mark.parametrize(
    ("groups", "count"),
    [
        ("solo", 10),
        ("all", 1),
        ("pairs", 5),
        ("trios", 4),
        ([[0, 1], [2, 3, 4]], 2),
    ],
)
def test_the_size_is_64_bytes_per_group(
    tmp_path: Path, groups: Any, count: int
) -> None:
    """The groups come from the pins of the board."""
    platform = load_platform(_write(tmp_path, _leds(groups)))
    check_equal(platform["_group_problems"], [])
    table = symbols(platform)
    check_equal(table["LEDR.size"], 64 * count)
    check_equal(table["LEDR.index"], 0)
    window = 1 << (64 * count - 1).bit_length()
    check_equal(table["LEDR.window"], window)


def test_the_runtime_header_has_the_base_of_each_group(tmp_path: Path) -> None:
    """`RV32_<NAME>_G<k>_BASE` is the base plus 64 bytes per group."""
    path = _write(tmp_path, _leds("pairs"))
    text = _write_runtime(tmp_path, path)
    check_in("#define RV32_LEDR_BASE RV32_ADDRESS(0x80002000)", text)
    check_in("#define RV32_LEDR_G0_BASE RV32_ADDRESS(0x80002000)", text)
    check_in("#define RV32_LEDR_G4_BASE RV32_ADDRESS(0x80002100)", text)


def _write_runtime(root: Path, platform: Path) -> str:
    """Render the runtime header of a platform."""
    data = yaml.safe_load(platform.read_text())
    data["generate"] = {"runtime": {"path": "out/m.h", "ram": "RAM"}}
    data["reserved"] = {}
    platform.write_text(yaml.safe_dump(data, sort_keys=False))
    return render_all(platform, root)[root / "out/m.h"]


def test_a_pin_in_no_group_is_off_and_noted(tmp_path: Path) -> None:
    """The note lists the off pins by board."""
    platform = load_platform(_write(tmp_path, _leds([[0, 1], [3]])))
    notes = memory_notes(platform)
    check_in("pins [2, 4, 5, 6, 7, 8, 9] are off on board small", notes[0])


def test_roles_follow_one_another(tmp_path: Path) -> None:
    """The pins of the second role come after the ones of the first."""
    block = {
        "PANEL": {
            "kind": "gpio",
            "roles": ["leds", "keys"],
            "base": 0x80006000,
            "groups": "all",
        }
    }
    platform = load_platform(_write(tmp_path, block))
    check_equal(platform["_group_problems"], [])
    plan = platform["peripherals"][0]["plan"]["small"]
    check_equal(plan["pins"], 14)
    check_equal(plan["dirs"], [2] * 10 + [1] * 4)
    check_equal(plan["active_low"], [False] * 10 + [True] * 4)


def test_the_display_block_has_one_group_per_digit_group(
    tmp_path: Path,
) -> None:
    """A `seg_display` takes the digits of the board."""
    block = {
        "HEX": {
            "kind": "seg_display",
            "base": 0x80005000,
            "groups": [[0, 1, 2, 3], [4, 5]],
        }
    }
    platform = load_platform(_write(tmp_path, block))
    check_equal(symbols(platform)["HEX.size"], 128)
    check_equal(platform["peripherals"][0]["plan"]["small"]["pins"], 6)


BAD_GROUPS: list[tuple[Any, str]] = [
    ([[0, 10]], "G-1"),
    ([[0, 1], [1, 2]], "G-2"),
    ([[]], "G-3"),
    ([list(range(33))], "G-1"),
    ("many", "G-5"),
]


@pytest.mark.parametrize(("groups", "code"), BAD_GROUPS)
def test_a_bad_group_is_refused(
    tmp_path: Path, groups: Any, code: str
) -> None:
    """Index out of range, repeated pin, empty or too big group."""
    path = _write(tmp_path, _leds(groups))
    with pytest.raises(ValueError, match=code):
        render_all(_with_generate(path), tmp_path)


def _with_generate(path: Path) -> Path:
    """Give the platform a `generate` entry so it is rendered."""
    data = yaml.safe_load(path.read_text())
    data["generate"] = {"runtime": {"path": "out/m.h", "ram": "RAM"}}
    data["reserved"] = {}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_a_group_with_more_than_32_pins_is_refused(tmp_path: Path) -> None:
    """D7: at most 32 pins in a group."""
    path = _write(
        tmp_path,
        {
            "SW": {
                "kind": "gpio",
                "role": "switches",
                "base": 0x80003000,
                "groups": "all",
            }
        },
        boards=["big"],
    )
    platform = load_platform(path)
    check_equal(platform["_group_problems"], [])
    platform = dict(platform)
    problems = [str(p) for p in validate_platform(platform)]
    check_equal([p for p in problems if "G-" in p], [])


def test_a_role_the_board_lacks_is_refused(tmp_path: Path) -> None:
    """The nano board has no switches."""
    block = {
        "SW": {
            "kind": "gpio",
            "role": "switches",
            "base": 0x80003000,
            "groups": "all",
        }
    }
    platform = load_platform(_write(tmp_path, block, boards=["nano"]))
    check_in(
        "G-4 peripheral SW: board nano has no role switches",
        str(platform["_group_problems"]),
    )


def test_every_board_of_the_platform_is_checked(tmp_path: Path) -> None:
    """Pin 12 exists on the big board only; the small one refuses it."""
    path = _write(tmp_path, _leds([[12]]), boards=["big", "small"])
    problems = load_platform(path)["_group_problems"]
    check(any("G-1" in p and "10 pins" in p for p in problems), str(problems))


def test_boards_with_another_number_of_groups_are_refused(
    tmp_path: Path,
) -> None:
    """`solo` gives 18 groups on one board and 10 on the other."""
    path = _write(tmp_path, _leds("solo"), boards=["big", "small"])
    problems = load_platform(path)["_group_problems"]
    check(any("G-6" in p for p in problems), str(problems))


def test_a_required_role_with_every_pin_off_is_a_warning(
    tmp_path: Path,
) -> None:
    """`io.leds.need: required` and no group at all."""
    path = _write(
        tmp_path,
        _leds([]),
        io={"leds": {"count": 10, "need": "required"}},
    )
    notes = memory_notes(load_platform(path))
    check(any(n.startswith("warning: role leds") for n in notes), str(notes))


def test_the_size_cannot_be_written(tmp_path: Path) -> None:
    """The window is derived from the groups."""
    block = _leds("all")
    block["LEDR"]["size"] = 64
    with pytest.raises(ValueError, match="derived from the groups"):
        load_platform(_write(tmp_path, block))


@pytest.mark.parametrize(
    ("change", "text"),
    [
        ({"kind": "uart"}, "kind must be one of"),
        ({"role": "leds", "roles": ["keys"]}, "exactly one of role and roles"),
        ({"role": "audio"}, "must be one of"),
        ({"other": 1}, "unknown keys"),
    ],
)
def test_a_bad_block_is_refused(
    tmp_path: Path, change: dict[str, Any], text: str
) -> None:
    """Each mistake of a block has its message."""
    block = _leds("all")
    block["LEDR"].update(change)
    with pytest.raises(ValueError, match=text):
        load_platform(_write(tmp_path, block))


def test_a_block_round_trips_through_the_test_writer(tmp_path: Path) -> None:
    """`to_layout` writes the kind, the role and the groups back."""
    platform = load_platform(_write(tmp_path, _leds("pairs")))
    written = to_layout({"peripherals": platform["peripherals"]})
    check_equal(
        written["peripherals"],
        {
            "LEDR": {
                "kind": "gpio",
                "base": 0x80002000,
                "groups": "pairs",
                "role": "leds",
            }
        },
    )


def test_the_platform_header_of_the_tests_is_generated(tmp_path: Path) -> None:
    """`generate.platform_h` writes the numbers of the platform."""
    path = _write(tmp_path, _leds("pairs"))
    data = yaml.safe_load(path.read_text())
    data["reserved"] = {
        "stdout": {"base": 0x4000FBE0, "size": 8},
        "tohost": {"base": 0x4000FFE8, "size": 8},
    }
    data["generate"] = {"platform_h": {"path": "out/rv32_platform.h"}}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    text = render_all(path, tmp_path)[tmp_path / "out/rv32_platform.h"]
    for line in (
        "#define RV32_RAM_BASE 0x40000000",
        "#define RV32_TOHOST 0x4000FFE8",
        "#define RV32_LEDR_BASE 0x80002000",
        "#define RV32_LEDR_G4_BASE 0x80002100",
        "#define RVMODEL_HALT_PASS",
    ):
        check_in(line, text)


def test_the_roles_of_general_use_number_their_pins_by_group(
    tmp_path: Path,
) -> None:
    """`gpio` has the pins of `GPIO_0` and then those of `GPIO_1`."""
    block = {
        "HEADERS": {
            "kind": "gpio",
            "role": "gpio",
            "base": 0x80100000,
            "groups": [[0, 35], [36, 71]],
        },
        "HSMC": {
            "kind": "gpio",
            "role": "hsmc",
            "base": 0x80200000,
            "groups": "pairs",
        },
    }
    platform = load_platform(_write(tmp_path, block, boards=["wide"]))
    check_equal(platform["_group_problems"], [])
    plans = [p["plan"]["wide"] for p in platform["peripherals"]]
    check_equal(plans[0]["pins"], 72)
    check_equal(plans[0]["dirs"], [0] * 72)
    check_equal(plans[1]["pins"], 21)
    check_equal(len(plans[1]["groups"]), 11)
    check_equal(symbols(platform)["HSMC.size"], 11 * 64)
