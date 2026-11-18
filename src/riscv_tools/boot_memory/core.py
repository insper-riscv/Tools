"""Build the shared bootloader of a project (its boot_memory.S).

The boot memory has no test source and no crt0 pairing, so it is built
once per invocation instead of once per test, and the caller reuses its
image.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools.bin_to_image.core import bin_to_hex
from riscv_tools.compiler.build import (
    C_STANDARD_FLAGS,
    elf_to_bin,
    elf_to_verilog_hex,
    run_gcc,
)


def boot_gcc_args(
    march: str,
    abi: str,
    linker: Path,
    source: Path,
    elf: Path,
    *extra: str,
) -> list[str]:
    """List the gcc arguments that build the boot memory.

    Parameters
    ----------
    march : str
        The `-march`, such as `rv32i` or `rv32e`.
    abi : str
        The `-mabi`, such as `ilp32` or `ilp32e`.
    linker : Path
        The linker script of the boot memory.
    source : Path
        The `boot_memory.S`.
    elf : Path
        The ELF to write.
    *extra : str
        More options, placed before the linker script.

    Returns
    -------
    list of str
        The arguments after the gcc binary.
    """
    return [
        f"-march={march}",
        f"-mabi={abi}",
        "-O0",
        *C_STANDARD_FLAGS,
        "-ffreestanding",
        "-nostdlib",
        "-nostartfiles",
        *extra,
        "-T",
        str(linker),
        str(source),
        "-o",
        str(elf),
    ]


@dataclass(frozen=True)
class BootMemoryOptions:
    """What varies between boot memory builds.

    Parameters
    ----------
    hex_format : str
        "words" for one 32-bit word per line, "verilog" for the
        `objcopy -O verilog` layout (see compiler.elf_to_verilog_hex).
    base : str
        The base ISA letter of the platform: `i` for RV32I (`ilp32`) or
        `e` for RV32E (`ilp32e`).
    """

    hex_format: str = "words"
    base: str = "i"


def build_boot_memory(
    toolchain_cfg: dict[str, Any],
    paths_cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    options: BootMemoryOptions | None = None,
) -> Path:
    """Compile boot_memory.S/.ld into a flat .bin, then a .hex.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section: needs `gcc` and
        `objcopy`.
    paths_cfg : dict of {str: Any}
        The project's `paths:` config section: needs `boot_memory` and
        `boot_memory_linker_script`.
    root : Path
        The consuming project's root directory; paths_cfg entries are
        resolved relative to this.
    build_dir : Path
        Directory to write boot_memory.elf/.bin/.hex into (created if
        missing).
    options : BootMemoryOptions, optional
        The hex layout and the base ISA; the defaults are one word per
        line and RV32I.

    Returns
    -------
    Path
        Path to the compiled boot_memory.hex.
    """
    options = options or BootMemoryOptions()
    base = options.base
    boot_memory_src = root / paths_cfg["boot_memory"]
    linker = root / paths_cfg["boot_memory_linker_script"]

    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / "boot_memory.elf"
    bin_ = build_dir / "boot_memory.bin"
    hex_ = build_dir / "boot_memory.hex"

    run_gcc(
        toolchain_cfg,
        boot_gcc_args(
            f"rv32{base}",
            "ilp32e" if base == "e" else "ilp32",
            linker,
            boot_memory_src,
            elf,
        ),
    )
    elf_to_bin(toolchain_cfg, elf, bin_)
    if options.hex_format == "verilog":
        elf_to_verilog_hex(toolchain_cfg, elf, hex_)
    else:
        bin_to_hex(bin_, hex_)
    return hex_
