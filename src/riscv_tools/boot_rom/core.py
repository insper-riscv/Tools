"""Build the shared bootloader of a project (its boot_rom.S).

The boot ROM has no test source and no crt0 pairing, so it is built
once per invocation instead of once per test, and the caller reuses its
image.
"""

from pathlib import Path
from typing import Any

from riscv_tools.bin_to_image.core import bin_to_hex
from riscv_tools.compiler.build import (
    elf_to_bin,
    elf_to_verilog_hex,
    run_gcc,
)


def build_boot_rom(
    toolchain_cfg: dict[str, Any],
    paths_cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    hex_format: str = "words",
) -> Path:
    """Compile boot_rom.S/boot_rom.ld into a flat .bin, then a .hex.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section: needs `gcc` and
        `objcopy`.
    paths_cfg : dict of {str: Any}
        The project's `paths:` config section: needs `boot_rom` and
        `boot_rom_linker_script`.
    root : Path
        The consuming project's root directory; paths_cfg entries are
        resolved relative to this.
    build_dir : Path
        Directory to write boot_rom.elf/.bin/.hex into (created if
        missing).
    hex_format : str, optional
        "words" for one 32-bit word per line, "verilog" for the
        `objcopy -O verilog` layout (see compiler.elf_to_verilog_hex).

    Returns
    -------
    Path
        Path to the compiled boot_rom.hex.
    """
    boot_rom_src = root / paths_cfg["boot_rom"]
    linker = root / paths_cfg["boot_rom_linker_script"]

    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / "boot_rom.elf"
    bin_ = build_dir / "boot_rom.bin"
    hex_ = build_dir / "boot_rom.hex"

    run_gcc(
        toolchain_cfg,
        [
            "-march=rv32i",
            "-mabi=ilp32",
            "-O0",
            "-ffreestanding",
            "-nostdlib",
            "-nostartfiles",
            "-T",
            str(linker),
            str(boot_rom_src),
            "-o",
            str(elf),
        ],
    )
    elf_to_bin(toolchain_cfg, elf, bin_)
    if hex_format == "verilog":
        elf_to_verilog_hex(toolchain_cfg, elf, hex_)
    else:
        bin_to_hex(bin_, hex_)
    return hex_
