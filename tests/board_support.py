"""Builders of a small board catalog and platform for the tests."""

import copy
from pathlib import Path
from typing import Any

import yaml

SDRAM_CHIP: dict[str, Any] = {
    "chip": "SDR-A",
    "kind": "sdram",
    "organization": {
        "words": 33554432,
        "width": 16,
        "banks": 4,
        "row_bits": 13,
        "col_bits": 10,
    },
    "cas_latency": 3,
    "timing": {"tck_ps": 7000, "trcd_ps": 15000},
    "io_timing": {"access_ns": 5.4},
    "max_mhz": 143,
    "source": "datasheet",
}
NOR_CHIP: dict[str, Any] = {
    "chip": "NOR-A",
    "kind": "nor",
    "organization": {"words": 8388608, "width": 8},
    "timing": {"access_ns": 90},
    "sector_bytes": 65536,
    "source": "inferido",
}
FAMILY: dict[str, Any] = {
    "family": "fam",
    "quartus_family": "Fam",
    "logic_unit": "le",
    "pll": {
        "ip": "altpll",
        "vco_mhz": [600, 1300],
        "clock_node_pattern": "<instance>|pll|clk[N]",
        "outputs_max": 2,
    },
    "block_ram": {"kind": "m9k", "bits_per_block": 9216},
    "memory_ip": "altsyncram",
    "virtual_jtag": True,
    "onchip_flash": None,
    "fmax": {"core_mhz_by_grade": {"C7": 64}},
    "calibration": "calibration/fam.yaml",
}
BOARD: dict[str, Any] = {
    "board": "bd",
    "name": "Board",
    "family": "fam",
    "device": "DEV",
    "speed_grade": "C7",
    "jtag": {
        "cable": "usb-blaster",
        "chain": [
            {
                "name": "DEV",
                "idcode": "020F70DD",
                "fpga": True,
                "confirmed": "measured",
            }
        ],
    },
    "resources": {
        "logic": {"unit": "le", "total": 1000},
        "block_ram": {"kind": "m9k", "blocks": 10, "bits_per_block": 9216},
        "multipliers": {"kind": "dsp9x9", "total": 4},
        "plls": 2,
        "user_pins": None,
    },
    "clocks": {
        "inputs": [{"name": "clk", "signal": "CLK", "mhz": 50}],
        "reference": "clk",
        "reset": {"signal": "RST", "active": "low"},
    },
    "io": {
        "leds": {"signals": "LED[9:0]", "active": "high"},
        "display": {"signals": "HEX[3:0][6:0]", "active": "low"},
    },
    "memories": {
        "sdram": {
            "chip": "SDR-A",
            "chips": 1,
            "signals": "DRAM",
            "clk_phase_ps": 4000,
        },
        "nor": {"chip": "NOR-A", "bus_width": 8, "signals": "FL"},
    },
    "console": {"default": "jtag", "uart": {"rx": "RX", "tx": "TX"}},
    "pins": "pins.yaml",
}
PLATFORM: dict[str, Any] = {
    "platform": "plat",
    "board": "bd",
    "regions": [
        {"name": "BOOT_MEMORY", "base": "0x0", "size": "4K", "kind": "rom"},
        {"name": "FLASH", "base": "0x1000", "size": "252K", "kind": "rom"},
        {"name": "RAM", "base": "0x40000000", "size": "64M", "kind": "ram"},
    ],
    "flash": {
        "region": "FLASH",
        "banks": [
            {"name": "A", "base": "0x1000", "size": "64K"},
            {"name": "B", "base": "0x11000", "size": "64K"},
        ],
    },
    "memory": {
        "rom": {
            "external": True,
            "backend": "emulado",
            "latency": {"first": 24, "next": 4},
            "sector_bytes": 4096,
        },
        "ram": {"external": True, "backend": "dispositivo", "device": "sdram"},
    },
    "clocks": {
        "core": {"mhz": 50, "phase_ps": 8250},
        "mem": {"mhz": 100},
    },
    "console": "jtag",
    "io": {"leds": {"count": 10, "need": "required"}},
}


def pin(name: str, number: str, confirmed: str = "repo") -> dict[str, str]:
    """Make one signal of a pins file.

    Parameters
    ----------
    name : str
        The signal.
    number : str
        The pin.
    confirmed : str, optional
        The seal of certainty.

    Returns
    -------
    dict of str to str
        The signal entry.
    """
    return {
        "name": name,
        "pin": number,
        "io_standard": "3.3-V LVTTL",
        "direction": "in",
        "confirmed": confirmed,
    }


def write(path: Path, data: Any) -> None:
    """Write a YAML file, creating the folders above it.

    Parameters
    ----------
    path : Path
        The file.
    data : Any
        The content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def write_catalog(
    root: Path,
    board: dict[str, Any] | None = None,
    family: dict[str, Any] | None = None,
    pins: list[dict[str, str]] | None = None,
) -> None:
    """Lay out a catalog with one board, its family and its chips.

    Parameters
    ----------
    root : Path
        The project root.
    board : dict of str to Any, optional
        The board; by default `BOARD`.
    family : dict of str to Any, optional
        The family; by default `FAMILY`.
    pins : list of dict of str to str, optional
        The signals; by default one per signal the board names.
    """
    data = board or copy.deepcopy(BOARD)
    write(root / "boards" / data["board"] / "board.yaml", data)
    write(root / "boards" / "families" / "fam.yaml", family or FAMILY)
    write(root / "Memory" / "chips" / "SDR-A.yaml", SDRAM_CHIP)
    write(root / "Memory" / "chips" / "NOR-A.yaml", NOR_CHIP)
    default = [pin("CLK", "M9"), pin("RST", "P22"), pin("DRAM_CLK", "A1")]
    default += [pin(f"LED[{i}]", f"L{i}") for i in range(10)]
    write(
        root / "boards" / data["board"] / "pins.yaml",
        {"board": data["board"], "device": "DEV", "signals": pins or default},
    )
    (root / "boards" / "calibration").mkdir(parents=True, exist_ok=True)
    (root / "boards" / "calibration" / "fam.yaml").write_text("family: fam\n")


def fresh_platform() -> dict[str, Any]:
    """Copy the base platform so a test can change it.

    Returns
    -------
    dict of str to Any
        A deep copy of `PLATFORM`.
    """
    return copy.deepcopy(PLATFORM)


def fresh_board() -> dict[str, Any]:
    """Copy the base board so a test can change it.

    Returns
    -------
    dict of str to Any
        A deep copy of `BOARD`.
    """
    return copy.deepcopy(BOARD)
