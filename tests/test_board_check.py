"""Tests of the provides and requires rules V1 to V10 and V15 to V19."""

from pathlib import Path
from typing import Any

import pytest
from catalog_support import (
    fresh_board,
    fresh_platform,
    pin,
    write,
    write_catalog,
)
from support import check, check_equal, check_in

from riscv_tools.board_check import (
    Finding,
    check_catalog,
    check_chain,
    check_platform,
)
from riscv_tools.board_schema import Board, Catalog
from riscv_tools.cli import main


def _run(
    root: Path,
    platform: dict[str, Any],
    board: dict[str, Any] | None = None,
) -> list[Finding]:
    """Lay out the catalog and check the platform against it."""
    write_catalog(root, board)
    return check_platform(platform, root)


def _texts(findings: list[Finding]) -> list[str]:
    """Format the findings as the messages the plan words."""
    return [str(finding) for finding in findings]


def test_the_base_platform_passes_without_a_message(tmp_path: Path) -> None:
    """The fixture is clean, so each test below breaks one thing."""
    check_equal(_run(tmp_path, fresh_platform()), [])


def test_a_platform_without_a_board_is_not_checked(tmp_path: Path) -> None:
    """The platforms written before the catalog keep passing."""
    platform = fresh_platform()
    del platform["board"]
    check_equal(_run(tmp_path, platform), [])


def test_auto_without_boards_checks_nothing(tmp_path: Path) -> None:
    """The identification by the JTAG happens at run time, not here."""
    platform = fresh_platform()
    platform["board"] = "auto"
    check_equal(_run(tmp_path, platform), [])


def test_v1_unknown_board(tmp_path: Path) -> None:
    """A board that is not in the catalog lists the known ones."""
    platform = fresh_platform()
    platform["board"] = "bd2"
    check_equal(
        _texts(_run(tmp_path, platform)),
        ["E board 'bd2' not found in boards/ (known: bd)"],
    )


def test_v1_unknown_family(tmp_path: Path) -> None:
    """A board whose family file is missing is refused."""
    board = fresh_board()
    board["family"] = "nope"
    check_equal(
        _texts(_run(tmp_path, fresh_platform(), board)),
        [
            "E family 'nope' of board 'bd' not found in boards/families/"
            " (known: fam)"
        ],
    )


def test_v1_unknown_chip(tmp_path: Path) -> None:
    """A board that names a chip the catalog lacks is refused."""
    board = fresh_board()
    board["memories"]["nor"]["chip"] = "NOR-X"
    messages = _texts(_run(tmp_path, fresh_platform(), board))
    check_in(
        "E chip 'NOR-X' of board 'bd' not found in chips/"
        " (known: NOR-A, SDR-A)",
        messages,
    )


def test_v1_a_malformed_board_is_reported(tmp_path: Path) -> None:
    """A schema problem of the board shows with its path."""
    board = fresh_board()
    board["speed_grade"] = 7
    messages = _texts(_run(tmp_path, fresh_platform(), board))
    check_equal(
        messages,
        ["E board 'bd' is invalid: board bd.speed_grade must be a string"],
    )


def test_v2_size_across_regions(tmp_path: Path) -> None:
    """Two regions that fit alone but not together are V2's."""
    platform = fresh_platform()
    platform["regions"].append(
        {"name": "RAM2", "base": "0x50000000", "size": "40M", "kind": "ram"}
    )
    platform["regions"][2]["size"] = "40M"
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "E platform 'plat' requires sdram (80M) but board 'bd' provides"
            " sdram of 64M"
        ],
    )


def test_v2_needs_of_the_closure(tmp_path: Path) -> None:
    """A `needs` type the board does not provide is an error."""
    board = fresh_board()
    del board["memories"]["nor"]
    platform = fresh_platform()
    platform["top"] = "top"
    (tmp_path / "paths.yaml").write_text(
        "repository: Top\nprovides:\n  top:\n    sources: [a.vhd]\n"
        "    requires: [leaf]\n    needs: [sdram]\n"
        "  leaf:\n    sources: [b.vhd]\n    needs: [nor, block_ram]\n"
    )
    for name in ("a.vhd", "b.vhd"):
        (tmp_path / name).write_text("")
    check_equal(
        _texts(_run(tmp_path, platform, board)),
        [
            "E platform 'plat' requires nor but board 'bd' provides:"
            " block_ram, sdram, vjtag"
        ],
    )


def test_v2_top_that_cannot_be_resolved(tmp_path: Path) -> None:
    """A top that no manifest declares is reported."""
    platform = fresh_platform()
    platform["top"] = ["ghost"]
    messages = _texts(_run(tmp_path, platform))
    check(messages[0].startswith("E top cannot be resolved"))


def test_v3_device_the_board_lacks(tmp_path: Path) -> None:
    """A backend dispositivo needs the device on the board."""
    board = fresh_board()
    del board["memories"]["nor"]
    platform = fresh_platform()
    platform["memory"]["rom"] = {
        "external": True,
        "backend": "dispositivo",
        "device": "nor",
    }
    check_equal(
        _texts(_run(tmp_path, platform, board)),
        [
            "E memory.rom.device nor is not provided by board 'bd'"
            " (provides: sdram); use backend emulado"
        ],
    )


def test_v4_console_on_pins_without_a_uart(tmp_path: Path) -> None:
    """The console on pins needs the UART of the board."""
    board = fresh_board()
    del board["console"]["uart"]
    platform = fresh_platform()
    platform["console"] = "pinos"
    check_equal(
        _texts(_run(tmp_path, platform, board)),
        [
            "E console pinos needs console.uart but board 'bd' declares none;"
            " use console jtag"
        ],
    )


def test_v5_required_role_missing_or_short(tmp_path: Path) -> None:
    """A required role the board lacks, or has fewer of, is an error."""
    platform = fresh_platform()
    platform["io"] = {
        "leds": {"count": 18, "need": "required"},
        "switches": {"count": 4, "need": "required"},
    }
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "E io.leds count 18 required but board 'bd' has 10",
            "E io.switches count 4 required but board 'bd' has none",
        ],
    )


def test_v6_optional_role_missing_or_short(tmp_path: Path) -> None:
    """An optional role only warns, and the peripheral is omitted."""
    platform = fresh_platform()
    platform["io"] = {
        "display": {"count": 6, "need": "optional"},
        "keys": {"count": 4, "need": "optional"},
    }
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "W io.display count 6 optional but board 'bd' has 4;"
            " the DISPLAY peripheral is omitted",
            "W io.keys optional and not on board 'bd';"
            " the KEYS peripheral is omitted",
        ],
    )


def test_v7_clock_over_the_chip_limit(tmp_path: Path) -> None:
    """The memory clock cannot pass the ceiling of the chip."""
    platform = fresh_platform()
    platform["clocks"]["mem"]["mhz"] = 150
    check_equal(
        _texts(_run(tmp_path, platform)),
        ["E clocks.mem 150 MHz exceeds chip SDR-A limit (143 MHz)"],
    )


def test_v7_clock_over_the_pll_range(tmp_path: Path) -> None:
    """No clock can pass the oscillator of the family."""
    platform = fresh_platform()
    platform["clocks"]["core"]["mhz"] = 2000
    messages = _texts(_run(tmp_path, platform))
    check_in(
        "E clocks.core 2000 MHz exceeds the PLL range of family 'fam'"
        " (1300 MHz)",
        messages,
    )


def test_v8_core_above_the_measured_fmax(tmp_path: Path) -> None:
    """A core clock above the measured Fmax only warns."""
    platform = fresh_platform()
    platform["clocks"]["core"]["mhz"] = 100
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "W clocks.core 100 MHz exceeds the measured Fmax (about 64 MHz,"
            " family fam, grade C7)"
        ],
    )


def test_v9_flash_bank_not_aligned_to_the_sector(tmp_path: Path) -> None:
    """The bank offset counts from the FLASH and aligns to the chip."""
    platform = fresh_platform()
    platform["memory"]["rom"] = {
        "external": True,
        "backend": "dispositivo",
        "device": "nor",
    }
    platform["flash"]["banks"][1]["base"] = "0x80000"
    platform["flash"]["banks"][0]["base"] = "0x1000"
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "E flash bank B base 0x7F000 is not a multiple of the NOR sector"
            " 0x10000 of chip NOR-A"
        ],
    )


def test_v9_emulated_sector(tmp_path: Path) -> None:
    """An emulated FLASH aligns to its own `sector_bytes`."""
    platform = fresh_platform()
    platform["flash"]["banks"][1]["base"] = "0x11800"
    check_equal(
        _texts(_run(tmp_path, platform)),
        [
            "E flash bank B base 0x10800 is not a multiple of the emulated"
            " sector 0x1000 (memory.rom.sector_bytes)"
        ],
    )


def test_v10_region_above_the_device(tmp_path: Path) -> None:
    """A region cannot be bigger than the device behind it."""
    platform = fresh_platform()
    platform["regions"][2]["size"] = "128M"
    check_equal(
        _texts(_run(tmp_path, platform)),
        ["E region RAM 128M exceeds SDRAM capacity 64M of board 'bd'"],
    )


def test_v15_more_clocks_than_pll_outputs(tmp_path: Path) -> None:
    """The distinct clocks and the DRAM clock need PLL outputs."""
    board = fresh_board()
    board["resources"]["plls"] = 1
    check_equal(
        _texts(_run(tmp_path, fresh_platform(), board)),
        ["E platform needs 3 PLL outputs on 2 PLLs; board 'bd' provides 1"],
    )


def test_v16_inferred_pin_in_use(tmp_path: Path) -> None:
    """A pin that is only inferred needs the option to be accepted."""
    pins = [pin("CLK", "M9"), pin("RST", "P22")]
    pins += [pin(f"LED[{i}]", f"L{i}") for i in range(10)]
    pins.append(pin("DRAM_CLK", "A1", "inferred"))
    pins.append(pin("SW[0]", "S1", "inferred"))
    write_catalog(tmp_path, None, None, pins)
    found = check_platform(fresh_platform(), tmp_path)
    check_equal(
        _texts(found),
        [
            "E pin A1 for DRAM_CLK is inferred, not confirmed;"
            " pass --accept-inferred-pins"
        ],
    )
    accepted = check_platform(
        fresh_platform(), tmp_path, accept_inferred_pins=True
    )
    check_equal(accepted, [])


def test_v17_chain_that_is_not_the_boards(tmp_path: Path) -> None:
    """The IDCODEs read from the cable must be the board's."""
    write_catalog(tmp_path)
    board: Board = Catalog.for_root(tmp_path).load_board("bd")
    check_equal(check_chain(board, "[1-3]", ["020f70dd"]), [])
    check_equal(
        _texts(check_chain(board, "[1-3]", ["02B050DD"])),
        [
            "E board 'bd' expects IDCODE 020F70DD on cable [1-3] but the chain"
            " has 02B050DD"
        ],
    )


def test_v18_family_without_calibration(tmp_path: Path) -> None:
    """A family whose calibration file is absent warns once."""
    (tmp_path / "boards" / "calibration").mkdir(parents=True)
    write_catalog(tmp_path)
    (tmp_path / "boards" / "calibration" / "fam.yaml").unlink()
    check_equal(
        _texts(check_platform(fresh_platform(), tmp_path)),
        [
            "W family 'fam' has no calibration; capacity estimate skipped,"
            " only the fit decides"
        ],
    )


def test_v18_capacity_that_is_not_known(tmp_path: Path) -> None:
    """A `null` capacity of the board warns."""
    board = fresh_board()
    board["resources"]["logic"]["total"] = None
    check_equal(
        _texts(_run(tmp_path, fresh_platform(), board)),
        [
            "W board 'bd' has no capacity for logic; its estimate is skipped,"
            " only the fit decides"
        ],
    )


@pytest.mark.parametrize(
    ("width", "message"),
    [
        (
            4,
            "E nor bus_width 4 needs 8 reads per word;"
            " backend nor supports 8, 16",
        ),
        (
            12,
            "E nor bus_width 12 does not divide the 32-bit word;"
            " backend nor supports 8, 16",
        ),
        (
            32,
            "E nor bus_width 32 needs 1 reads per word;"
            " backend nor supports 8, 16",
        ),
    ],
)
def test_v19_bus_width_the_backend_cannot_slice(
    tmp_path: Path, width: int, message: str
) -> None:
    """The width of the NOR must be one the backend supports."""
    board = fresh_board()
    board["memories"]["nor"]["bus_width"] = width
    platform = fresh_platform()
    platform["memory"]["rom"] = {
        "external": True,
        "backend": "dispositivo",
        "device": "nor",
    }
    platform["flash"]["banks"] = []
    check_equal(_texts(_run(tmp_path, platform, board)), [message])


def test_a_platform_with_a_wrong_field_is_a_schema_error(
    tmp_path: Path,
) -> None:
    """The board fields of the platform are typed."""
    platform = fresh_platform()
    platform["clocks"]["core"]["mhz"] = "fast"
    write(tmp_path / "unused.yaml", {})
    found = _run(tmp_path, platform)
    check_equal(
        _texts(found), ["E platform platform.clocks.core.mhz must be a number"]
    )


def test_the_catalog_check_finds_what_a_board_cites_wrongly(
    tmp_path: Path,
) -> None:
    """A signal that is not in the pins file, or a pin used twice."""
    board = fresh_board()
    del board["io"]["display"]
    board["io"]["leds"]["signals"] = "LED[11:0]"
    pins = [pin("CLK", "M9"), pin("RST", "M9"), pin("DRAM_CLK", "A1")]
    pins += [pin("RX", "R1"), pin("TX", "R2")]
    pins += [pin(f"LED[{i}]", f"L{i}") for i in range(10)]
    write_catalog(tmp_path, board, None, pins)
    problems = check_catalog(Catalog.for_root(tmp_path))
    check_equal(
        problems,
        [
            "board bd: io.leds cites LED[10], which is not in pins",
            "board bd: io.leds cites LED[11], which is not in pins",
            "board bd: memories.nor cites FL_, which is not in pins",
            "board bd: pin M9 is used by CLK, RST and is not in conflicts",
        ],
    )


def test_the_catalog_check_passes_a_consistent_catalog(
    tmp_path: Path,
) -> None:
    """The fixture catalog is consistent but for the NOR pins."""
    pins = [pin("CLK", "M9"), pin("RST", "P22"), pin("DRAM_CLK", "A1")]
    pins += [pin(f"LED[{i}]", f"L{i}") for i in range(10)]
    pins += [pin("FL_CE", "F1"), pin("RX", "R1"), pin("TX", "R2")]
    pins += [
        pin(f"HEX{i}[{j}]", f"H{i}{j}") for i in range(4) for j in range(7)
    ]
    write_catalog(tmp_path, None, None, pins)
    check_equal(check_catalog(Catalog.for_root(tmp_path)), [])


def test_the_subcommands_exit_with_the_findings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check-memory-map` fails on a board error."""
    platform = fresh_platform()
    platform["clocks"]["mem"]["mhz"] = 150
    platform["memory"]["icache"] = {"enabled": False}
    platform["memory"]["dcache"] = {"enabled": False}
    write_catalog(tmp_path)
    write(tmp_path / "plat.yaml", platform)
    argv = ["riscv-tools", "--root", str(tmp_path)]
    monkeypatch.setattr(
        "sys.argv", [*argv, "check-memory-map", "--platform", "plat.yaml"]
    )
    with pytest.raises(SystemExit) as caught:
        main()
    check_equal(caught.value.code, 1)
    check_in(
        "BOARD V7 E clocks.mem 150 MHz exceeds chip", capsys.readouterr().err
    )
    monkeypatch.setattr("sys.argv", [*argv, "check-boards"])
    with pytest.raises(SystemExit) as caught:
        main()
    check_equal(caught.value.code, 1)


def test_a_device_the_board_lacks_does_not_break_the_other_rules(
    tmp_path: Path,
) -> None:
    """V3 reports it, and the clock rules still run without the chip."""
    board = fresh_board()
    del board["memories"]["sdram"]
    messages = _texts(_run(tmp_path, fresh_platform(), board))
    check_equal(
        messages,
        [
            "E memory.ram.device sdram is not provided by board 'bd'"
            " (provides: nor); use backend emulado"
        ],
    )
