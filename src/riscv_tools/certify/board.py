"""Run the ACT4 ELFs on the board, from the SDRAM.

The ELFs of the SDRAM target (see tools/riscv_build/act/rv32im-sdram/) are one flat
image that starts at the base of the SDRAM. On the board the host loads each one through
the SDRAM debug port while the core is parked in the boot ROM, then lets the core go:

1. Once: the FLASH gets a three-instruction stub (`fence.i`, `lui t0, base`, `jr t0`).
   The boot ROM jumps to the FLASH after every restart, and the stub sends the core to
   the ELF; the `fence.i` drops whatever the instruction cache still holds of the
   previous ELF.
2. For each ELF: the region of the SDRAM that the ELF may use is zeroed (the board does
   it), the image is written, the go flag restarts the core, and the host reads the HTIF
   `tohost` word from the SDRAM until it holds an odd value (1 is a PASS) or the time
   runs out.

The board must be programmed with the SDRAM platform and the core parked, as it is after
`riscv-tools run` or right after the programming.
"""

import struct
import time
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    mailbox,
    ram_target,
    rom_writer,
    sdram_debug,
)
from riscv_tools.certify import core as certify_core
from riscv_tools.jtag import JtagLink

_FENCE_I = 0x0000100F
_JR_T0 = 0x00028067
_SHT_SYMTAB = 2
_ELF32_SHDR = struct.Struct("<IIIIIIIIII")
_ELF32_SYM = struct.Struct("<IIIBBH")
_ELF32_HEADER_SHOFF = struct.Struct("<I")


def flash_stub_words(sdram_base: int) -> list[int]:
    """Return the FLASH stub that sends the core to the ELF in the SDRAM.

    Parameters
    ----------
    sdram_base : int
        First address of the SDRAM, 4 KiB aligned.

    Returns
    -------
    list of int
        `fence.i`, `lui t0, base` and `jr t0`.
    """
    if sdram_base & 0xFFF:
        raise ValueError(f"the SDRAM base {sdram_base:#x} is not 4 KiB aligned")
    lui_t0 = (sdram_base & 0xFFFFF000) | (5 << 7) | 0x37
    return [_FENCE_I, lui_t0, _JR_T0]


def elf_symbol(elf: Path, name: str) -> int:
    """Read the address of a symbol from the symbol table of a 32-bit ELF.

    Parameters
    ----------
    elf : Path
        The ELF file.
    name : str
        The symbol, for example `tohost`.

    Returns
    -------
    int
        The address of the symbol.

    Raises
    ------
    KeyError
        The ELF has no symbol of that name.
    """
    data = elf.read_bytes()
    (shoff,) = _ELF32_HEADER_SHOFF.unpack_from(data, 32)
    shentsize, shnum = struct.unpack_from("<HH", data, 46)
    for index in range(shnum):
        header = _ELF32_SHDR.unpack_from(data, shoff + index * shentsize)
        kind, offset, size = header[1], header[4], header[5]
        link, entsize = header[6], header[9]
        if kind != _SHT_SYMTAB or not entsize:
            continue
        str_header = _ELF32_SHDR.unpack_from(data, shoff + link * shentsize)
        str_offset = str_header[4]
        for sym in range(size // entsize):
            sym_name, value, *_ = _ELF32_SYM.unpack_from(data, offset + sym * entsize)
            end = data.index(b"\0", str_offset + sym_name)
            if data[str_offset + sym_name : end].decode() == name:
                return value
    raise KeyError(f"{elf} has no symbol {name!r}")


def image_words(elf: Path, sdram_base: int) -> list[int]:
    """Return the words of the ELF image that starts at the base of the SDRAM.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF of the SDRAM target.
    sdram_base : int
        First address of the SDRAM.

    Returns
    -------
    list of int
        The 32-bit words from `sdram_base` to the last byte of the ELF below the
        HTIF words, little-endian, zero padded to a whole word.
    """
    tohost = elf_symbol(elf, "tohost")
    segments = certify_core.load_segments(elf)
    image = certify_core.region_image(segments, sdram_base, tohost)
    image += bytes(-len(image) % 4)
    return [int.from_bytes(image[i : i + 4], "little") for i in range(0, len(image), 4)]


def write_flash_stub(
    link: JtagLink, cfg: dict[str, Any], build_dir: Path, sdram_base: int
) -> None:
    """Write the stub into the FLASH over JTAG.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The merged project config: memory.rom_words and quartus.rom_mem_instances.
    build_dir : Path
        Where the scratch image files go.
    sdram_base : int
        First address of the SDRAM.
    """
    stub = b"".join(w.to_bytes(4, "little") for w in flash_stub_words(sdram_base))
    bin_path = build_dir / "flash_stub.bin"
    mif_path = build_dir / "flash_stub.mif"
    bin_path.write_bytes(stub)
    bin_to_image.bin_to_mif(bin_path, mif_path, int(cfg["memory"]["rom_words"]))
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instances"], mif_path)


def run_elf(  # noqa: PLR0913, PLR0917
    link: JtagLink,
    cfg: dict[str, Any],
    elf: Path,
    sdram_base: int,
    region_words: int,
    timeout_s: float,
) -> tuple[bool | None, int, float]:
    """Load one ELF into the SDRAM, run it and read its `tohost`.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    cfg : dict of {str: Any}
        The merged project config: memory.ram_base/go_flag_addr and the RAM backend.
    elf : Path
        The ACT4 ELF.
    sdram_base : int
        First address of the SDRAM.
    region_words : int
        Words of the SDRAM that the ELF may use, zeroed before the load.
    timeout_s : float
        How long to wait for `tohost`.

    Returns
    -------
    tuple of (bool or None, int, float)
        True for a PASS, False for a FAIL, None for a timeout; the number of words
        loaded; the seconds from the go flag to the end.
    """
    tohost_word = (elf_symbol(elf, "tohost") - sdram_base) // 4
    words = image_words(elf, sdram_base)
    sdram_debug.fill(link, 0, region_words, 0)
    sdram_debug.load_words(link, 0, words)

    target = ram_target.target_from_config(cfg)
    mailbox.pulse_go_flag(
        link, target, cfg["memory"]["ram_base"], cfg["memory"]["go_flag_addr"]
    )
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        (tohost,) = sdram_debug.read_words(link, tohost_word, 1)
        if tohost & 1:
            return tohost == 1, len(words), time.monotonic() - started
    return None, len(words), time.monotonic() - started


def run_suite_on_board(  # noqa: PLR0913
    cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    link: JtagLink,
    only: list[str] | None = None,
    *,
    build: bool = True,
) -> dict[str, bool | None]:
    """Build the ACT4 ELFs of the SDRAM target and run each one on the board.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: act.vendor_dir/target_config/extensions/jobs/
        sdram_base/sdram_region_bytes/board_timeout_s, memory and quartus.
    root : Path
        The consuming project's root directory.
    build_dir : Path
        Where scratch files go.
    link : JtagLink
        Which JTAG cable/chip to use.
    only : list of str, optional
        Names of the ELFs to run (without the extension); all when omitted.
    build : bool, optional
        Build the ELFs with ACT4's own `make` first. With False the ELFs that an
        earlier build left under the ACT4 work directory are used: the build needs the
        Ruby and Sail toolchain, which a machine with the board may not have.

    Returns
    -------
    dict of {str: bool or None}
        The result of each ELF run: True PASS, False FAIL, None timeout.
    """
    act_cfg = cfg["act"]
    sdram_base = int(str(act_cfg["sdram_base"]), 0)
    region_words = int(str(act_cfg.get("sdram_region_bytes", 0x100000)), 0) // 4
    timeout_s = float(act_cfg.get("board_timeout_s", 30))
    target_config = root / act_cfg["target_config"]
    if build:
        elfs_dir = certify_core.build_elfs(
            root / act_cfg["vendor_dir"],
            target_config,
            act_cfg["extensions"],
            act_cfg["jobs"],
        )
    else:
        name = certify_core.target_name(target_config)
        elfs_dir = root / act_cfg["vendor_dir"] / "work" / name / "elfs"
    elfs = [
        e for e in certify_core.discover_elfs(elfs_dir) if not only or e.stem in only
    ]
    build_dir.mkdir(parents=True, exist_ok=True)
    write_flash_stub(link, cfg, build_dir, sdram_base)

    results: dict[str, bool | None] = {}
    for elf in elfs:
        passed, words, seconds = run_elf(
            link, cfg, elf, sdram_base, region_words, timeout_s
        )
        results[elf.stem] = passed
        verdict = {True: "PASS", False: "FAIL", None: "TIMEOUT"}[passed]
        print(f"{elf.stem}: {verdict} ({words * 4} bytes, {seconds:.1f}s)")
    return results
