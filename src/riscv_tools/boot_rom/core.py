"""Build the fixed, shared bootloader (see a project's own boot_rom.S).

A distinct concern from `compiler` (per-test .c/.S -> .elf/.bin):
BOOT_ROM is built ONCE per invocation, not per test — it has no test
source, no crt0 pairing, and isn't part of any test's own manifest.
Every consumer that needs its image (sim_runner for GHDL, rom_writer/
orchestrator for real hardware) calls `build_boot_rom` once and reuses
the result, the same way a test's own compiled .hex gets reused across
sim_runner.run_suite's manifest loop rather than rebuilt per test.
"""

import subprocess
from pathlib import Path
from typing import Any

from riscv_tools.bin_to_image.core import bin_to_hex


def build_boot_rom(
    toolchain_cfg: dict[str, Any], paths_cfg: dict[str, Any], root: Path, build_dir: Path
) -> Path:
    """Compile boot_rom.S/boot_rom.ld into a flat binary and convert it to .hex.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section — needs `gcc` and
        `objcopy`.
    paths_cfg : dict of {str: Any}
        The project's `paths:` config section — needs `boot_rom` and
        `boot_rom_linker_script`.
    root : Path
        The consuming project's root directory — paths_cfg entries are
        resolved relative to this.
    build_dir : Path
        Directory to write boot_rom.elf/.bin/.hex into (created if
        missing).

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

    subprocess.run(
        [
            str(toolchain_cfg["gcc"]),
            # boot_rom.S is plain RV32I (li/lw/sw/branches/jr) -- no
            # M-extension instructions, unlike a project's own tests
            # (isa.default_ext) -- fixed rather than threaded through
            # from isa: config a project's tests use for themselves.
            "-march=rv32i",
            "-mabi=ilp32",
            "-O0",
            "-ffreestanding",
            "-nostdlib",
            "-nostartfiles",
            f"-Wl,-T,{linker}",
            str(boot_rom_src),
            "-o",
            str(elf),
        ],
        check=True,
    )
    subprocess.run(
        [str(toolchain_cfg["objcopy"]), "-O", "binary", str(elf), str(bin_)], check=True
    )
    bin_to_hex(bin_, hex_)
    return hex_
