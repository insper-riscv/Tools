"""Tests of the readers of the board, family, chip and pins files."""

from pathlib import Path
from typing import Any

import pytest
from catalog_support import (
    FAMILY,
    NOR_CHIP,
    SDRAM_CHIP,
    fresh_board,
    fresh_platform,
    write,
    write_catalog,
)
from support import check, check_equal, check_in

from riscv_tools.board_schema import (
    Catalog,
    NotFoundError,
    SchemaError,
    declares_board,
    expand_group,
    group_count,
    parse_board,
    parse_chip,
    parse_family,
    parse_pins,
    parse_platform_fields,
)
from riscv_tools.board_schema.platform_fields import read_platform_file


def test_a_chip_extends_another_by_name(tmp_path: Path) -> None:
    """The extending chip keeps what it does not say and overrides."""
    write_catalog(tmp_path)
    write(
        tmp_path / "Memory" / "chips" / "SDR-B.yaml",
        {"chip": "SDR-B", "extends": "SDR-A", "source": "inferido"},
    )
    chip = Catalog.for_root(tmp_path).load_chip("SDR-B")
    check_equal(chip.chip, "SDR-B")
    check_equal(chip.source, "inferido")
    check_equal(chip.kind, "sdram")
    check_equal(chip.capacity_bytes, 64 * 1024 * 1024)
    check_equal(chip.timing, SDRAM_CHIP["timing"])


def test_a_chip_extends_loop_is_refused(tmp_path: Path) -> None:
    """Two chips that extend each other are an error, not a hang."""
    write_catalog(tmp_path)
    for name, other in (("L1", "L2"), ("L2", "L1")):
        write(
            tmp_path / "Memory" / "chips" / f"{name}.yaml",
            {"chip": name, "extends": other},
        )
    with pytest.raises(SchemaError, match="extends"):
        Catalog.for_root(tmp_path).load_chip("L1")


def test_a_chip_file_must_carry_its_own_name(tmp_path: Path) -> None:
    """The name inside the file is the name of the file."""
    write_catalog(tmp_path)
    write(tmp_path / "Memory" / "chips" / "X.yaml", {**NOR_CHIP})
    with pytest.raises(SchemaError, match="field chip is 'NOR-A'"):
        Catalog.for_root(tmp_path).load_chip("X")


def test_unknown_names_list_what_exists(tmp_path: Path) -> None:
    """A missing board, family or chip says what the catalog has."""
    write_catalog(tmp_path)
    catalog = Catalog.for_root(tmp_path)
    for load, kind in (
        (catalog.load_board, "board"),
        (catalog.load_family, "family"),
        (catalog.load_chip, "chip"),
    ):
        with pytest.raises(NotFoundError) as caught:
            load("nope")
        check_equal(caught.value.kind, kind)
        check(caught.value.known)


def test_the_catalog_reads_a_board_with_its_pins(tmp_path: Path) -> None:
    """The board, its family and its pins load together."""
    write_catalog(tmp_path)
    catalog = Catalog.for_root(tmp_path)
    board = catalog.load_board("bd")
    check_equal(board.memories["sdram"].signals, ("DRAM",))
    check_equal(board.jtag.chain[0].idcode, "020F70DD")
    check_equal(catalog.load_family("fam").pll.outputs_max, 2)
    check_equal(len(catalog.load_pins("bd", board)), 13)


def test_chip_problems_are_all_reported() -> None:
    """Every wrong field shows, each with its path."""
    chip: dict[str, Any] = {**SDRAM_CHIP, "kind": "dram", "typo": 1}
    del chip["timing"]
    with pytest.raises(SchemaError) as caught:
        parse_chip(chip)
    check_equal(
        caught.value.problems,
        [
            "chip.kind must be one of sdram, sram, nor, serial_flash",
            "chip.timing is required",
            "chip.typo is not a field of the schema",
        ],
    )


def test_an_sdram_chip_needs_its_organization() -> None:
    """The banks and the address bits are required for an SDRAM."""
    chip: dict[str, Any] = {**SDRAM_CHIP}
    chip["organization"] = {"words": 1, "width": 16}
    with pytest.raises(SchemaError) as caught:
        parse_chip(chip)
    check_in("chip.organization.banks is required", caught.value.problems)


def test_family_types_are_checked() -> None:
    """A wrong type or a reversed oscillator range is refused."""
    family: dict[str, Any] = {**FAMILY, "virtual_jtag": "yes"}
    family["pll"] = {**FAMILY["pll"], "vco_mhz": [1300, 600]}
    with pytest.raises(SchemaError) as caught:
        parse_family(family)
    check_equal(
        caught.value.problems,
        [
            "family.pll.vco_mhz must be [min, max] with min not above max",
            "family.virtual_jtag must be true or false",
        ],
    )


def test_a_board_must_name_exactly_one_fpga() -> None:
    """A chain without the FPGA flag is refused."""
    board = fresh_board()
    board["jtag"]["chain"][0]["fpga"] = False
    with pytest.raises(SchemaError, match="exactly one FPGA"):
        parse_board(board)


def test_a_board_accepts_the_fields_of_the_boards_package() -> None:
    """Cable name, USB ids, HPS devices and prefix lists are fields."""
    board = fresh_board()
    board["target_level"] = "N2"
    board["jtag"]["cable_name"] = "DE-SoC [USB-1]"
    board["jtag"]["usb"] = [
        {"id": "09fb:6010", "state": "before", "confirmed": "inferred"}
    ]
    board["jtag"]["samd21"] = {"sketch": "USBBlaster"}
    board["jtag"]["external_pads"] = {"status": "pending"}
    board["jtag"]["chain"].insert(
        0, {"name": "SOCVHPS", "idcode": "4BA00477", "hps": True}
    )
    board["memories"]["sdram"]["signals"] = ["oSDRAM", "bSDRAM"]
    board["memories"]["serial_flash"] = {
        "chip": None,
        "bytes": 2097152,
        "shared_with_config": True,
    }
    parsed = parse_board(board)
    check(parsed.jtag.chain[0].hps)
    check_equal(parsed.jtag.usb[0].usb_id, "09fb:6010")
    check_equal(parsed.memories["sdram"].signals, ("oSDRAM", "bSDRAM"))
    check_equal(parsed.jtag.cable_name, "DE-SoC [USB-1]")


def test_a_board_rejects_a_wrong_idcode_and_unknown_key() -> None:
    """An IDCODE is 8 hexadecimal digits, and a typo is a problem."""
    board = fresh_board()
    board["jtag"]["chain"][0]["idcode"] = "XYZ"
    board["colour"] = "red"
    with pytest.raises(SchemaError) as caught:
        parse_board(board)
    check_equal(
        caught.value.problems,
        [
            "board.jtag.chain[0].idcode must be 8 hexadecimal digits",
            "board.colour is not a field of the schema",
        ],
    )


def test_pins_signals_and_conflicts() -> None:
    """The pins file takes `conflicts` and checks the seals."""
    raw: dict[str, Any] = {
        "board": "bd",
        "device": "DEV",
        "conflicts": [{"pin": "L4", "signals": ["A", "B"], "note": "x"}],
        "signals": [
            {
                "name": "A",
                "pin": "L4",
                "io_standard": "3.3-V LVTTL",
                "direction": "in",
                "confirmed": "guess",
            }
        ],
    }
    with pytest.raises(SchemaError) as caught:
        parse_pins(raw)
    check_equal(
        caught.value.problems,
        ["pins.signals[0].confirmed must be one of manual, repo, inferred"],
    )


def test_signal_groups_expand_as_the_format_says() -> None:
    """A bus, a bus of buses and a single signal."""
    check_equal(expand_group("LEDR[2:0]"), ["LEDR[0]", "LEDR[1]", "LEDR[2]"])
    check_equal(
        expand_group("HEX[1:0][1:0]"),
        [
            "HEX0[0]",
            "HEX0[1]",
            "HEX1[0]",
            "HEX1[1]",
        ],
    )
    check_equal(expand_group("KEY[0]"), ["KEY[0]"])
    check_equal(expand_group("CLOCK_50"), ["CLOCK_50"])
    check_equal(group_count("HEX[5:0][6:0]"), 6)
    check_equal(group_count("LEDR[9:0]"), 10)
    check_equal(group_count("CLOCK_50"), 1)


def test_platform_fields_are_read_and_typed() -> None:
    """The new fields of the platform load with their defaults."""
    platform = fresh_platform()
    fields = parse_platform_fields(platform)
    check(declares_board(platform))
    check_equal(fields.candidates(), ("bd",))
    check_equal(fields.memories["rom"].latency, (24, 4))
    check_equal(fields.clocks["core"].phase_ps, 8250)
    check_equal(fields.console, "jtag")
    check_equal(fields.io["leds"].count, 10)


_DELETE = object()
PLATFORM_CASES: list[tuple[tuple[str, ...], str, object, str]] = [
    (
        ("memory", "ram"),
        "backend",
        _DELETE,
        "platform.memory.ram.backend is required when external is true",
    ),
    (
        ("memory", "ram"),
        "device",
        "nor",
        "platform.memory.ram.device must be one of sdram, sram",
    ),
    (
        ("memory", "ram"),
        "latency",
        {"first": 1},
        "platform.memory.ram.latency.next is required",
    ),
    (
        ("memory", "rom"),
        "sector_bytes",
        3000,
        "platform.memory.rom.sector_bytes must be a power of 2",
    ),
    (
        ("memory", "rom"),
        "device",
        "nor",
        "platform.memory.rom.device is only valid with the backend"
        " dispositivo",
    ),
    (
        ("clocks",),
        "mem",
        _DELETE,
        "platform.clocks.mem is required with a device",
    ),
    (
        (),
        "console",
        "uart",
        "platform.console must be one of jtag, pinos",
    ),
    (
        ("io",),
        "leds",
        {"count": 10, "need": "maybe"},
        "platform.io.leds.need must be one of required, optional",
    ),
    (
        ("io",),
        "buzzer",
        {"count": 1, "need": "required"},
        "platform.io.buzzer is not a role "
        "(leds, switches, keys, display, video)",
    ),
]


@pytest.mark.parametrize(("path", "key", "value", "problem"), PLATFORM_CASES)
def test_platform_field_problems(
    path: tuple[str, ...], key: str, value: object, problem: str
) -> None:
    """Each misuse of the new fields is a typed problem."""
    platform = fresh_platform()
    node: Any = platform
    for step in path:
        node = node[step]
    if value is _DELETE:
        del node[key]
    else:
        node[key] = value
    with pytest.raises(SchemaError) as caught:
        parse_platform_fields(platform)
    check_in(problem, caught.value.problems)


def test_platform_extends_is_resolved_by_the_config_reader(
    tmp_path: Path,
) -> None:
    """A platform variant says only what differs from its base."""
    write(tmp_path / "base.yaml", fresh_platform())
    write(
        tmp_path / "variant.yaml",
        {"extends": "base.yaml", "clocks": {"core": {"mhz": 40}}},
    )
    merged = read_platform_file(tmp_path / "variant.yaml")
    check_equal(merged["clocks"]["core"], {"mhz": 40, "phase_ps": 8250})
    check_equal(merged["board"], "bd")
