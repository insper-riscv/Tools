"""Tests for the `config_pkg` that is generated from a platform."""

import argparse
import shutil
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
    check_not_in,
    profile_matrix,
)

from riscv_tools import cli
from riscv_tools.memory_map import (
    check_all,
    check_memory_map,
    load_platform,
    render_all,
    write_all,
)
from riscv_tools.memory_map.config_pkg import (
    parse_overrides,
    render_variant,
)

REAL = Path(__file__).resolve().parent / "fixtures" / "real_platform"
REAL_PLATFORM = "src/cyclone-v/de0-cv/platform.yaml"

MATRIX = profile_matrix("rv32i", "rv32e", "rv64i")

PLATFORM: dict[str, Any] = {
    "profile": "rv32im_zicntr",
    "profiles": "matrix.yaml",
    "extras": ["Interrupts", "AccessFaults"],
    "regions": MAP_REGIONS,
    "reserved": MAP_RESERVED,
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "peripherals": [
        {"name": "UART", "base": "0xC0000000", "id": 4},
        {"name": "CLINT", "base": "0xE0000000", "id": 6},
    ],
    "console": "jtag",
    "memory": {
        "rom": {"external": True},
        "ram": {"external": False},
        "icache": {"enabled": True, "size_bits": 4096},
        "dcache": {"enabled": False},
    },
    "generate": {
        "vhdl": {
            "rom": "FLASH",
            "ram": "RAM",
            "package": "map_pkg",
            "path": "out/map_pkg.vhd",
        },
        "config_pkg": {"path": "out/config_pkg.vhd"},
    },
}

SMALL: dict[str, Any] = {
    **PLATFORM,
    "address_bits": 24,
    "regions": [
        {"name": "BOOT_MEMORY", "base": "0x0", "size": "2K", "exec": True},
        {"name": "FLASH", "base": "0x800", "size": "30K", "exec": True},
        {"name": "RAM", "base": "0x8000", "size": "160K", "kind": "ram"},
    ],
    "peripherals": [
        {"name": "UART", "base": "0xC00000", "id": 4},
        {"name": "CLINT", "base": "0xE00000", "id": 6},
    ],
}

WIDE: dict[str, Any] = {
    **PLATFORM,
    "profile": "rv64im_zicntr",
    "address_bits": 40,
    "peripherals": [
        {"name": "UART", "base": "0xC000000000", "id": 4},
        {"name": "CLINT", "base": "0xE000000000", "id": 6},
    ],
}


def _write(root: Path, platform: dict[str, Any]) -> Path:
    """Write the platform and the matrix of its profiles."""
    (root / "matrix.yaml").write_text(yaml.safe_dump(MATRIX))
    path = root / "platform.yaml"
    path.write_text(yaml.safe_dump(platform, sort_keys=False))
    return path


def _config(
    root: Path,
    platform: dict[str, Any],
    **overrides: bool | int,
) -> str:
    """Render the `config_pkg` of a platform or of a variant of it."""
    path = _write(root, platform)
    return render_variant(load_platform(path), path, root, overrides)


def _has(text: str, *lines: str) -> None:
    """Check that every line is in the text."""
    for line in lines:
        check_in(line, text)


def test_a_32_bit_platform_gets_the_defaults_of_today(tmp_path: Path) -> None:
    """Without `address_bits` the package is the RV32 one of 32 bits."""
    text = _config(tmp_path, PLATFORM)
    _has(
        text,
        "constant IS_64              : boolean := false;",
        "constant IS_BASE_E          : boolean := false;",
        "constant ADDR_BITS          : natural := 32;",
        "constant XLEN               : natural := 32;",
        "constant NUM_REGS           : natural := 32;",
        "constant REG_BITS           : natural := 5;",
        "subtype word_t is std_logic_vector((XLEN - 1) downto 0);",
        "subtype map_addr_t is unsigned(ADDR_BITS downto 0);",
        "constant HAS_M              : boolean := true;",
        "constant HAS_ZICNTR         : boolean := true;",
        "constant HAS_ZIHPM          : boolean := false;",
        "constant HAS_INTERRUPTS     : boolean := true;",
        "constant HAS_ACCESS_FAULTS  : boolean := true;",
        "constant HAS_ICACHE         : boolean := true;",
        "constant HAS_DCACHE         : boolean := false;",
        "constant ROM_EXTERNAL       : boolean := true;",
        "constant RAM_EXTERNAL       : boolean := false;",
        "constant BOOT_MEMORY_BITS   : natural := 11;",
        "constant CACHE_WINDOW_BITS  : natural := 26;",
        "constant ROM_BASE           : map_addr_t :=",
        'unsigned\'(x"000000800")',
        'unsigned\'(x"000008000")',
        "constant PERIPH_BASE        : map_addr_t :=",
        'unsigned\'(x"080000000")',
        'constant PERIPH_SLOTS       : periph_slots_t := "01010000";',
        "constant HAS_UART           : boolean := true;",
        "constant HAS_UART_JTAG      : boolean := true;",
        "constant HAS_UART_PINS      : boolean := false;",
        "constant HAS_CLINT          : boolean := true;",
        "constant HAS_PLIC           : boolean := false;",
    )


def test_the_composed_constants_and_the_functions_are_written(
    tmp_path: Path,
) -> None:
    """The composed constants and the two functions are written."""
    text = _config(tmp_path, PLATFORM)
    _has(
        text,
        ":= HAS_M or HAS_ZMMUL;",
        ":= HAS_ZICNTR or HAS_ZIHPM;",
        ":= HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS;",
        "function isa_string return string;",
        "function check_isa return boolean;",
        "end package body config_pkg;",
        'if HAS_ZICNTR then\n\t\t\tadd("_zicntr");',
    )
    check(text.startswith("-- " + "=" * 69 + "\n"), "72 columns")
    check_not_in("std_logic_arith", text)


def test_a_24_bit_platform_narrows_the_package(tmp_path: Path) -> None:
    """`address_bits: 24` gives a 7-digit window and a 24-bit tag."""
    text = _config(tmp_path, SMALL)
    _has(
        text,
        "constant ADDR_BITS          : natural := 24;",
        "constant XLEN               : natural := 32;",
        "constant CACHE_WINDOW_BITS  : natural := 24;",
        'unsigned\'(x"0800000")',
        'constant PERIPH_SLOTS       : periph_slots_t := "01010000";',
    )


def test_a_64_bit_platform_gets_the_wide_package(tmp_path: Path) -> None:
    """An rv64 profile with 40 address bits gives 64-bit words."""
    text = _config(tmp_path, WIDE)
    _has(
        text,
        "constant IS_64              : boolean := true;",
        "constant ADDR_BITS          : natural := 40;",
        "constant XLEN               : natural := 64;",
        "constant NUM_REGS           : natural := 32;",
        'unsigned\'(x"08000000000")',
    )


def test_the_base_e_has_16_registers_of_4_bits(tmp_path: Path) -> None:
    """The E base gives `NUM_REGS` 16 and `REG_BITS` 4."""
    text = _config(tmp_path, {**PLATFORM, "profile": "rv32em_zicntr"})
    _has(
        text,
        "constant IS_BASE_E          : boolean := true;",
        "constant NUM_REGS           : natural := 16;",
        "constant REG_BITS           : natural := 4;",
        'add("e");',
    )


def test_a_variant_changes_the_width_and_the_base(tmp_path: Path) -> None:
    """`IS_64` and `ADDR_BITS` of a variant replace the platform's."""
    text = _config(tmp_path, PLATFORM, IS_64=True, ADDR_BITS=40)
    _has(
        text,
        "-- Variante: IS_64=true.",
        "-- Variante: ADDR_BITS=40.",
        "constant IS_64              : boolean := true;",
        "constant XLEN               : natural := 64;",
        "constant ADDR_BITS          : natural := 40;",
        # As bases dos periféricos seguem a janela da nova largura.
        'unsigned\'(x"08000000000")',
    )
    flipped = _config(tmp_path, PLATFORM, HAS_ZIHPM=True, IS_BASE_E=True)
    _has(
        flipped,
        "constant HAS_ZIHPM          : boolean := true;",
        "constant IS_BASE_E          : boolean := true;",
        "constant NUM_REGS           : natural := 16;",
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ADDR_BITS": 40}, "V-A2"),
        ({"ADDR_BITS": 70}, "address_bits must be an integer"),
        ({"ADDR_BITS": 16}, "V-A3"),
        ({"HAS_FOO": True}, "HAS_FOO"),
    ],
)
def test_an_invalid_variant_is_refused(
    tmp_path: Path, overrides: dict[str, bool | int], message: str
) -> None:
    """A variant is checked as a platform of its own."""
    with pytest.raises(ValueError, match=message):
        _config(tmp_path, PLATFORM, **overrides)


def test_parse_overrides_reads_booleans_and_the_width() -> None:
    """`--set` takes booleans and an integer for `ADDR_BITS`."""
    check_equal(
        parse_overrides(["is_64=True", "ADDR_BITS=40", "HAS_M=false"]),
        {"IS_64": True, "ADDR_BITS": 40, "HAS_M": False},
    )
    for bad in ("IS_64", "ADDR_BITS=x", "IS_64=1", "=true"):
        with pytest.raises(ValueError, match="--set"):
            parse_overrides([bad])


def test_the_uart_follows_the_console(tmp_path: Path) -> None:
    """The kind of UART comes from `console` or from its name."""
    pins = _config(tmp_path, {**PLATFORM, "console": "pins"})
    _has(
        pins,
        "constant HAS_UART_PINS      : boolean := true;",
        "constant HAS_UART_JTAG      : boolean := false;",
    )
    named = _config(
        tmp_path,
        {
            **PLATFORM,
            "peripherals": [
                {"name": "UART_JTAG", "base": "0xC0000000", "id": 4}
            ],
        },
    )
    _has(
        named,
        "constant HAS_UART           : boolean := false;",
        "constant HAS_UART_JTAG      : boolean := true;",
    )


def test_the_rom_and_the_ram_must_be_named(tmp_path: Path) -> None:
    """Without `generate.vhdl` or `config` the map has no ROM or RAM."""
    bare = {k: v for k, v in PLATFORM.items() if k != "generate"}
    with pytest.raises(ValueError, match="ROM and the RAM"):
        _config(tmp_path, bare)
    named = {**bare, "config": {"rom": "FLASH", "ram": "RAM"}}
    check_in("constant ADDR_BITS", _config(tmp_path, named))


def test_generate_writes_the_config_pkg_and_check_catches_a_change(
    tmp_path: Path,
) -> None:
    """The file is part of the generated set that `--check` compares."""
    platform = _write(tmp_path, PLATFORM)
    files = render_all(platform, tmp_path)
    check_in(tmp_path / "out/config_pkg.vhd", list(files))
    check_in(tmp_path / "out/map_pkg.vhd", list(files))
    written = write_all(platform, tmp_path)
    check_equal(len(written), 2)
    count, problems = check_all(platform, tmp_path)
    check_equal(count, 2)
    check_equal(problems, [])
    (tmp_path / "out/config_pkg.vhd").write_text("hand edited\n")
    _, problems = check_all(platform, tmp_path)
    check_equal([str(p.file) for p in problems], ["out/config_pkg.vhd"])


def test_check_memory_map_compares_the_two_packages(tmp_path: Path) -> None:
    """The constants both packages carry must agree on disk."""
    platform = _write(tmp_path, PLATFORM)
    _, problems = check_memory_map(platform, tmp_path)
    check_equal([p.detail for p in problems], ["file not found"] * 2)
    write_all(platform, tmp_path)
    check_equal(check_memory_map(platform, tmp_path)[1], [])
    config = tmp_path / "out/config_pkg.vhd"
    config.write_text(
        config.read_text().replace(
            "HAS_ICACHE         : boolean := true",
            "HAS_ICACHE         : boolean := false",
        )
    )
    _, problems = check_memory_map(platform, tmp_path)
    check_equal(len(problems), 1)
    check_in("HAS_ICACHE is False but HAS_ICACHE of", str(problems[0]))
    write_all(platform, tmp_path)
    config.write_text(
        config.read_text().replace(
            'unsigned\'(x"000008000")', 'unsigned\'(x"000008400")'
        )
    )
    _, problems = check_memory_map(platform, tmp_path)
    check_in("ROM_END is 33792 but ROM_END_KIB", str(problems[0]))


def test_a_platform_without_config_pkg_is_not_compared(
    tmp_path: Path,
) -> None:
    """A platform with no `config_pkg` entry runs nothing new."""
    platform = {
        **PLATFORM,
        "generate": {"vhdl": PLATFORM["generate"]["vhdl"]},
    }
    path = _write(tmp_path, platform)
    check_equal(len(render_all(path, tmp_path)), 1)
    write_all(path, tmp_path)
    count, problems = check_memory_map(path, tmp_path)
    check_equal(count, 0)
    check_equal(problems, [])


def test_cmd_generate_config_pkg_prints_and_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command prints or writes the package, or fails."""
    _write(tmp_path, PLATFORM)
    args = argparse.Namespace(
        root=str(tmp_path),
        platform="platform.yaml",
        set=["IS_64=true", "ADDR_BITS=40"],
        output=None,
    )
    cli.cmd_generate_config_pkg(args)
    out = capsys.readouterr().out
    _has(
        out,
        "package config_pkg is",
        "constant XLEN               : natural := 64;",
    )
    args.output = "rtl/config_pkg.vhd"
    cli.cmd_generate_config_pkg(args)
    check_in("generated:", capsys.readouterr().out)
    check_equal((tmp_path / "rtl/config_pkg.vhd").read_text(), out)
    args.set = ["ADDR_BITS=70"]
    with pytest.raises(SystemExit) as exc:
        cli.cmd_generate_config_pkg(args)
    check_equal(exc.value.code, 1)
    check_in("ERROR address_bits", capsys.readouterr().err)


def test_the_real_platform_files_do_not_change(tmp_path: Path) -> None:
    """The DE0-CV map package is the one written before."""
    shutil.copytree(REAL, tmp_path, dirs_exist_ok=True)
    platform = tmp_path / REAL_PLATFORM
    files = render_all(platform, tmp_path)
    expected = (REAL / "expected/de0_cv_map_pkg.vhd").read_text()
    check_equal(
        files[tmp_path / "src/cyclone-v/de0-cv/de0_cv_map_pkg.vhd"], expected
    )


def test_the_real_platform_config_pkg_is_stable(tmp_path: Path) -> None:
    """The DE0-CV `config_pkg` is the frozen one and agrees."""
    shutil.copytree(REAL, tmp_path, dirs_exist_ok=True)
    platform = tmp_path / REAL_PLATFORM
    text = render_variant(load_platform(platform), platform, tmp_path)
    check_equal(text, (REAL / "expected/config_pkg.vhd").read_text())
    data = load_platform(platform)
    data["generate"]["config_pkg"] = {"path": "rtl/config_pkg.vhd"}
    data.pop("checks", None)
    platform.write_text(yaml.safe_dump(data, sort_keys=False))
    write_all(platform, tmp_path)
    check_equal(check_memory_map(platform, tmp_path)[1], [])
