"""Tests of the external kinds: registry, validation and board roles."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from peripherals_support import EXAMPLES, FIXTURES, catalog, request
from support import (
    ZICSR_INTERRUPTS_PLATFORM,
    check,
    check_equal,
    check_in,
    check_not_in,
    write_zicsr_platform,
)

from riscv_tools.board_check import check_catalog, check_platform
from riscv_tools.board_generate import generate
from riscv_tools.board_inputs import InputError, load_inputs
from riscv_tools.board_ports import build_ports
from riscv_tools.board_schema import Catalog
from riscv_tools.fit_estimate.table import (
    DEFAULT_VOCABULARY,
    EXTERNAL_TERMS,
    allowed_paths,
)
from riscv_tools.memory_map import load_platform, render_all, validate_platform
from riscv_tools.memory_map.kinds import EXTERNAL, KINDS
from riscv_tools.memory_map.platform_format import normalize

GENERATE = {
    "vhdl": {
        "path": "gen/ext_map_pkg.vhd",
        "package": "ext_map_pkg",
        "rom": "FLASH",
        "ram": "RAM",
    }
}
CLINT = {"name": "CLINT", "base": "0xE0000000", "size": "64K"}
PLIC = {"name": "PLIC", "base": "0xF0000000", "size": "4M"}


def _entry(name: str, kind: str, base: int, **extra: Any) -> dict[str, Any]:
    """Write one external peripheral."""
    return {"name": name, "kind": kind, "base": f"{base:#x}", **extra}


def _platform(
    tmp_path: Path, peripherals: list[dict[str, Any]], **interrupts: Any
) -> Path:
    """Write a platform with the PLIC and the peripherals."""
    section = {"clock_hz": 50000000, "mtime_hz": 1000000}
    section |= interrupts or {"plic": {"priority_bits": 3}}
    return write_zicsr_platform(
        tmp_path,
        {
            **ZICSR_INTERRUPTS_PLATFORM,
            "peripherals": [CLINT, PLIC, *peripherals],
            "interrupts": section,
            "generate": GENERATE,
        },
    )


def _problems(tmp_path: Path, items: list[dict[str, Any]]) -> list[str]:
    """Validate a platform and list the messages."""
    path = _platform(tmp_path, items)
    return [str(p) for p in validate_platform(load_platform(path))]


def test_every_kind_has_an_example_platform() -> None:
    """The examples are exactly the external kinds of the registry."""
    # O exemplo `eth_rgmii` é o modo RGMII do `eth`, não outro kind.
    kinds = (set(EXAMPLES) - {"eth_rgmii"}) | {"sd_native"}
    check_equal(sorted(EXTERNAL), sorted(kinds))
    check_in("gpio", KINDS)
    check_in("timer", KINDS)


def test_an_unknown_kind_is_refused_with_the_known_ones(
    tmp_path: Path,
) -> None:
    """The message of a bad kind lists every kind of the registry."""
    path = _platform(tmp_path, [_entry("X", "vga", 0x80000000, size=64)])
    with pytest.raises(ValueError, match="kind must be one of") as raised:
        load_platform(path)
    for kind in ("ps2", "sd_spi", "adc", "gpio", "timer"):
        check_in(kind, str(raised.value))


@pytest.mark.parametrize("kind", EXAMPLES)
def test_the_example_platform_is_valid(kind: str, tmp_path: Path) -> None:
    """The peripherals of each example pass the map validation."""
    data = yaml.safe_load(
        (FIXTURES / "platforms" / f"{kind}.yaml").read_text(encoding="utf-8")
    )
    items = [
        {"name": name, **value}
        for name, value in data["peripherals"].items()
        if name not in ("CLINT", "PLIC")
    ]
    check_equal(_problems(tmp_path, items), [])


def test_a_window_under_the_registers_is_refused(tmp_path: Path) -> None:
    """V-P11: the registers of the entity do not fit."""
    found = _problems(tmp_path, [_entry("SD", "sd_spi", 0x80008000, size=16)])
    check(any("V-P11" in text and "32 bytes" in text for text in found))


def test_the_window_defaults_to_the_registers(tmp_path: Path) -> None:
    """`size` is optional and takes the registers of the entity."""
    path = _platform(tmp_path, [_entry("ETH0", "eth", 0x80008100)])
    text = render_all(path, tmp_path)[tmp_path / "gen/ext_map_pkg.vhd"]
    check_in("constant ETH0_BASE : addr_t", text)


def test_a_variant_field_is_checked(tmp_path: Path) -> None:
    """V-P12: the chip of an ADC is required and must be known."""
    missing = _problems(tmp_path, [_entry("A", "adc", 0x80010000)])
    check(
        any(
            "V-P12" in text and "`chip` is required" in text
            for text in missing
        )
    )
    wrong = _problems(
        tmp_path, [_entry("A", "adc", 0x80010000, chip="ads1115")]
    )
    check(any("V-P12" in text and "must be one of" in text for text in wrong))


def test_two_peripherals_on_one_instance_are_refused(tmp_path: Path) -> None:
    """V-P13: the same instance of a role cannot be taken twice."""
    found = _problems(
        tmp_path,
        [
            _entry("A", "i2c", 0x80010000, instance=0),
            _entry("B", "i2c", 0x80010100, instance=0),
        ],
    )
    check(any("V-P13" in text for text in found))


def test_a_pinned_line_cannot_be_a_fixed_one(tmp_path: Path) -> None:
    """V-P10 also holds for an external peripheral with a line."""
    path = _platform(
        tmp_path,
        [_entry("IR", "ir", 0x80009000)],
        plic={"priority_bits": 3},
        sources=[{"name": "IR", "id": 3}],
    )
    found = [str(p) for p in validate_platform(load_platform(path))]
    check(any("V-P10" in text for text in found))


def test_a_field_of_another_kind_is_refused(tmp_path: Path) -> None:
    """An entry cannot carry a key its kind does not know."""
    path = _platform(
        tmp_path, [_entry("SD", "sd_spi", 0x80008000, three_wire=True)]
    )
    with pytest.raises(ValueError, match="unknown keys"):
        load_platform(path)


def test_each_peripheral_with_a_line_gets_a_source(tmp_path: Path) -> None:
    """Timers and external peripherals share the free lines from 5."""
    path = _platform(
        tmp_path,
        [
            _entry("KBD", "ps2", 0x80007000),
            _entry("SD", "sd_spi", 0x80008000),
            _entry("VIDEO", "video", 0x80100000),
            _entry("T0", "timer", 0x80006000, size=64),
        ],
    )
    text = render_all(path, tmp_path)[tmp_path / "gen/ext_map_pkg.vhd"]
    check_in("constant IRQ_KBD : positive := 5;", text)
    check_in("constant IRQ_SD : positive := 7;", text)
    check_in("constant IRQ_T0 : positive := 8;", text)
    check_not_in("IRQ_VIDEO", text)
    check_in("constant EXT_COUNT : natural := 3;", text)
    check_in("constant SD_EXT_POS : natural := 1;", text)


def test_a_platform_without_external_peripherals_has_no_table(
    tmp_path: Path,
) -> None:
    """The generated package is the same as before without the kinds."""
    text = render_all(_platform(tmp_path, []), tmp_path)[
        tmp_path / "gen/ext_map_pkg.vhd"
    ]
    check_not_in("EXT_COUNT", text)


def test_the_catalog_of_the_example_board_is_clean(tmp_path: Path) -> None:
    """`check-boards` reads the bus roles and finds every signal."""
    catalog(tmp_path)
    found = check_catalog(Catalog.for_root(tmp_path))
    check_equal(found, [])


def test_a_bus_role_that_cites_a_missing_signal_is_a_problem(
    tmp_path: Path,
) -> None:
    """A signal of `buses` that the pins file lacks is reported."""
    boards = catalog(tmp_path)
    path = boards / "example" / "board.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("IRDA_RXD}", "IRDA_NONE}"), encoding="utf-8")
    found = check_catalog(Catalog.for_root(tmp_path))
    check(any("IRDA_NONE" in text and "buses.ir[0]" in text for text in found))


def test_the_board_schema_refuses_a_bad_bus_role(tmp_path: Path) -> None:
    """Unknown roles, pins and chips and a missing pin are problems."""
    boards = catalog(tmp_path)
    path = boards / "example" / "board.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "  usbx: {a: b}\n", encoding="utf-8")
    with pytest.raises(Exception, match="not a bus role"):
        Catalog.for_root(tmp_path).load_board("example")
    text = path.read_text(encoding="utf-8").replace("  usbx: {a: b}\n", "")
    text = text.replace("{rxd: IRDA_RXD}", "{rxx: IRDA_RXD}")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(Exception, match="rxd"):
        Catalog.for_root(tmp_path).load_board("example")


@pytest.mark.parametrize("kind", EXAMPLES)
def test_the_example_checks_clean_against_the_board(
    kind: str, tmp_path: Path
) -> None:
    """`check_platform` gives no error for any example."""
    req = request(tmp_path, kind)

    platform = yaml.safe_load(req.platform_file.read_text(encoding="utf-8"))
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    errors = [str(f) for f in found if f.level == "E"]
    check_equal(errors, [])


def test_the_ports_of_the_example_are_the_pins_of_the_role(
    tmp_path: Path,
) -> None:
    """The ports carry the name, width, direction and owner."""
    req = request(tmp_path, "sd_spi")
    inputs = load_inputs(
        req.platform_file, None, req.boards_dir, req.chips_dir
    )
    ports = {p.name: p for p in build_ports(inputs).ports if p.owner}
    check_equal(sorted(ports), ["SD_CLK", "SD_CMD", "SD_DAT"])
    check_equal(ports["SD_DAT"].width, 4)
    check_equal(ports["SD_CMD"].direction, "inout")
    check_equal(ports["SD_CLK"].owner, "SD")
    check_equal(ports["SD_CLK"].pin, "clk")


def test_a_required_peripheral_the_board_lacks_is_an_error(
    tmp_path: Path,
) -> None:
    """The second copy of a role does not exist on a board with one."""
    req = request(tmp_path, "sd_spi")
    text = req.platform_file.read_text(encoding="utf-8").replace(
        "  SD: {kind: sd_spi, base: 0x80008000}\n",
        "  SD: {kind: sd_spi, base: 0x80008000}\n"
        "  SDN: {kind: sd_native, base: 0x80008100}\n",
    )
    req.platform_file.write_text(text, encoding="utf-8")
    with pytest.raises(InputError, match="instance 1 is needed"):
        generate(req)


def test_an_optional_peripheral_the_board_lacks_is_omitted(
    tmp_path: Path,
) -> None:
    """`need: optional` turns the error into a warning."""
    req = request(tmp_path, "sd_spi")
    text = req.platform_file.read_text(encoding="utf-8").replace(
        "  SD: {kind: sd_spi, base: 0x80008000}\n",
        "  SD: {kind: sd_spi, base: 0x80008000}\n"
        "  SDN: {kind: sd_native, base: 0x80008100, need: optional}\n",
    )
    req.platform_file.write_text(text, encoding="utf-8")
    inputs = load_inputs(
        req.platform_file, None, req.boards_dir, req.chips_dir
    )
    plan = build_ports(inputs)
    check_equal(
        [p.name for p in plan.ports if p.owner], ["SD_CLK", "SD_CMD", "SD_DAT"]
    )
    check(any("SDN" in w and "omitted" in w for w in plan.warnings))


def _checked(tmp_path: Path, kind: str, accept: bool = True) -> list[str]:
    """Check an example against the board and list the findings."""
    req = request(tmp_path, kind)
    platform = yaml.safe_load(req.platform_file.read_text(encoding="utf-8"))
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=accept)
    return [f"{f.rule} {f}" for f in found]


def test_an_inferred_pin_of_a_peripheral_needs_the_flag(
    tmp_path: Path,
) -> None:
    """V16 reaches the pins of the bus roles in use."""
    found = _checked(tmp_path, "ir", accept=False)
    check(any(text.startswith("V16") and "IRDA_RXD" in text for text in found))
    check_equal([t for t in found if t.startswith("V16")][1:], [])


def test_a_board_without_the_role_gets_v23(tmp_path: Path) -> None:
    """V23 is an error if required and a warning if optional."""
    req = request(tmp_path, "ps2")
    text = req.platform_file.read_text(encoding="utf-8").replace(
        "boards: [example]", "boards: [de0-cv]"
    )
    text = text.replace("board: example", "board: de0-cv")
    req.platform_file.write_text(text, encoding="utf-8")
    platform = yaml.safe_load(text)
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    texts = [f"{f.rule} {f.level} {f.text}" for f in found if f.rule == "V23"]
    check(any("E" in t and "no bus role ps2" in t for t in texts))
    optional = text.replace(
        "kind: ps2, device: keyboard,",
        "kind: ps2, need: optional, device: keyboard,",
    ).replace(
        "kind: ps2, device: mouse,",
        "kind: ps2, need: optional, device: mouse,",
    )
    platform = yaml.safe_load(optional)
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    check(
        all(f.level == "W" for f in found if f.rule == "V23"),
        "an optional peripheral is only a warning",
    )


def test_the_external_entities_are_terms_of_the_calibration() -> None:
    """The fit table accepts one term for each entity."""
    names = {f"peripherals.{t}" for t in EXTERNAL_TERMS}
    check_in("PS2_KEYBOARD", EXTERNAL_TERMS)
    check_in("LTC2308", EXTERNAL_TERMS)
    check_in("peripherals.HDMI_TX", names)
    check_in(
        "peripherals.HDMI_TX", allowed_paths(DEFAULT_VOCABULARY) or set[str]()
    )


def test_an_entity_without_measure_is_a_warning_not_an_error(
    tmp_path: Path,
) -> None:
    """V18 names the terms of the entities that have no coefficient."""
    req = request(tmp_path, "i2c")
    family = req.boards_dir / "families" / "cyclone-iv-e.yaml"
    family.write_text(
        family.read_text(encoding="utf-8").replace(
            "calibration: null", "calibration: calibration/cyclone-iv-e.yaml"
        ),
        encoding="utf-8",
    )
    table = req.boards_dir / "calibration" / "cyclone-iv-e.yaml"
    table.parent.mkdir()
    table.write_text(
        "family: cyclone-iv-e\nunit: le\n"
        "coefficients:\n  core: {rv32i: 1000}\n",
        encoding="utf-8",
    )
    platform = yaml.safe_load(req.platform_file.read_text(encoding="utf-8"))
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    v18 = [f for f in found if f.rule == "V18" and "I2C_MASTER" in f.text]
    check_equal([f.level for f in v18], ["W"])
    check_equal([f for f in found if f.level == "E"], [])
