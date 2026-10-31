"""Run the ACT4 ELFs on the board, from the SDRAM.

The ELFs of the SDRAM target (see tools/riscv_build/act/rv32im-sdram/)
are one flat image that starts at the base of the SDRAM. On the board
the host loads each one through the SDRAM debug port while the core is
parked in the boot ROM, then lets the core go:

1. Once: the FLASH gets a three-instruction stub (`fence.i`, `lui t0,
base`, `jr t0`).
   The boot ROM jumps to the FLASH after every restart, and the stub
   sends the core to the ELF; the `fence.i` drops whatever the
   instruction cache still holds of the previous ELF.
2. For each ELF: the region of the SDRAM that the ELF may use is zeroed
(the board does
   it), the image is written, the go flag restarts the core, and the
   host reads the HTIF `tohost` word from the SDRAM until it holds an
   odd value (1 is a PASS) or the time runs out.
3. With `act.board_display` set, the display shows `AC` on HEX5 and HEX4
and the number
   of the ELF in the session, in decimal and counted from 1, on HEX3 to
   HEX0 (`AC0001` to `AC0059`). The first red LED lights when an ELF
   fails or times out and stays lit until the next session.

The board must be programmed with the SDRAM platform and the core
parked, as it is after `riscv-tools run` or right after the programming.
"""

import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

from riscv_tools import (
    bin_to_image,
    display,
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
    """Return the FLASH stub that sends the core to the SDRAM ELF.

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
        raise ValueError(
            f"the SDRAM base {sdram_base:#x} is not 4 KiB aligned"
        )
    lui_t0 = (sdram_base & 0xFFFFF000) | (5 << 7) | 0x37
    return [_FENCE_I, lui_t0, _JR_T0]


def elf_symbol(elf: Path, name: str) -> int:
    """Read a symbol address from the symbol table of a 32-bit ELF.

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
            sym_name, value, *_ = _ELF32_SYM.unpack_from(
                data, offset + sym * entsize
            )
            end = data.index(b"\0", str_offset + sym_name)
            if data[str_offset + sym_name : end].decode() == name:
                return value
    raise KeyError(f"{elf} has no symbol {name!r}")


def image_words(elf: Path, sdram_base: int) -> list[int]:
    """Return the words of the ELF image that starts at the SDRAM base.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF of the SDRAM target.
    sdram_base : int
        First address of the SDRAM.

    Returns
    -------
    list of int
        The 32-bit words from `sdram_base` to the last byte of the ELF
        below the HTIF words, little-endian, zero padded to a whole
        word.
    """
    tohost = elf_symbol(elf, "tohost")
    segments = certify_core.load_segments(elf)
    image = certify_core.region_image(segments, sdram_base, tohost)
    image += bytes(-len(image) % 4)
    return [
        int.from_bytes(image[i : i + 4], "little")
        for i in range(0, len(image), 4)
    ]


def write_flash_stub(
    link: JtagLink, cfg: dict[str, Any], build_dir: Path, sdram_base: int
) -> None:
    """Write the stub into the FLASH over JTAG.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to write to.
    cfg : dict of {str: Any}
        The merged project config: memory.rom_base, memory.rom_words and
        quartus.rom_mem_instances.
    build_dir : Path
        Where the scratch image files go.
    sdram_base : int
        First address of the SDRAM.
    """
    stub = b"".join(
        w.to_bytes(4, "little") for w in flash_stub_words(sdram_base)
    )
    bin_path = build_dir / "flash_stub.bin"
    mif_path = build_dir / "flash_stub.mif"
    bin_path.write_bytes(stub)
    # The FLASH is addressed raw by the instruction bus, so the stub
    # sits at the word index of memory.rom_base, where the boot ROM
    # jumps to (the same padding `compile` gives an image).
    pad_words = int(cfg["memory"]["rom_base"]) // 4
    bin_to_image.bin_to_mif(
        bin_path,
        mif_path,
        depth=pad_words + int(cfg["memory"]["rom_words"]),
        pad_words=pad_words,
    )
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instances"], mif_path)


@dataclass(frozen=True)
class SdramRegion:
    """Where and for how long an ELF runs in the SDRAM."""

    base: int
    words: int
    timeout_s: float


def run_elf(
    link: JtagLink,
    cfg: dict[str, Any],
    elf: Path,
    region: SdramRegion,
) -> tuple[bool | None, int, float]:
    """Load one ELF into the SDRAM, run it and read its `tohost`.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to use.
    cfg : dict of {str: Any}
        The merged project config: memory.ram_base/go_flag_addr and the
        RAM backend.
    elf : Path
        The ACT4 ELF.
    region : SdramRegion
        The first address of the SDRAM, the words of it that the ELF
        may use (zeroed before the load) and how long to wait for
        `tohost`.

    Returns
    -------
    tuple of (bool or None, int, float)
        True for a PASS, False for a FAIL, None for a timeout; the
        number of words loaded; the seconds from the go flag to the end.
    """
    tohost_word = (elf_symbol(elf, "tohost") - region.base) // 4
    words = image_words(elf, region.base)
    sdram_debug.fill(link, 0, region.words, 0)
    sdram_debug.load_words(link, 0, words)

    target = ram_target.target_from_config(cfg)
    mailbox.pulse_go_flag(
        link, target, cfg["memory"]["ram_base"], cfg["memory"]["go_flag_addr"]
    )
    started = time.monotonic()
    while time.monotonic() - started < region.timeout_s:
        (tohost,) = sdram_debug.read_words(link, tohost_word, 1)
        if tohost & 1:
            return tohost == 1, len(words), time.monotonic() - started
    return None, len(words), time.monotonic() - started


class BoardOptions(TypedDict, total=False):
    """The optional settings of `run_suite_on_board`."""

    build: bool


def _find_elfs(
    act_cfg: dict[str, Any],
    root: Path,
    only: list[str] | None,
    *,
    build: bool,
) -> list[Path]:
    """List the ACT4 ELFs to run, building them first when asked.

    Parameters
    ----------
    act_cfg : dict of {str: Any}
        The `act` section of the config.
    root : Path
        The consuming project's root directory.
    only : list of str or None
        Names of the ELFs to keep; all when empty or None.
    build : bool
        Build with ACT4's own `make` first.

    Returns
    -------
    list of Path
        The ELFs to run.
    """
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
    return [
        e
        for e in certify_core.discover_elfs(elfs_dir)
        if not only or e.stem in only
    ]


def run_suite_on_board(
    cfg: dict[str, Any],
    root: Path,
    build_dir: Path,
    link: JtagLink,
    only: list[str] | None = None,
    **options: Unpack[BoardOptions],
) -> dict[str, bool | None]:
    """Build the SDRAM target ACT4 ELFs and run each one on the board.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config:
        act.vendor_dir/target_config/extensions/jobs/
        sdram_base/sdram_region_bytes/board_timeout_s, memory and
        quartus.
    root : Path
        The consuming project's root directory.
    build_dir : Path
        Where scratch files go.
    link : JtagLink
        Which JTAG cable/chip to use.
    only : list of str, optional
        Names of the ELFs to run (without the extension); all when
        omitted.
    **options : Unpack[BoardOptions]
        The keyword settings, described below.
    build : bool, optional
        Build the ELFs with ACT4's own `make` first. With False the ELFs
        that an earlier build left under the ACT4 work directory are
        used: the build needs the Ruby and Sail toolchain, which a
        machine with the board may not have.

    Returns
    -------
    dict of {str: bool or None}
        The result of each ELF run: True PASS, False FAIL, None timeout.
    """
    act_cfg = cfg["act"]
    sdram_base = int(str(act_cfg["sdram_base"]), 0)
    region_words = (
        int(str(act_cfg.get("sdram_region_bytes", 0x100000)), 0) // 4
    )
    region = SdramRegion(
        base=sdram_base,
        words=region_words,
        timeout_s=float(act_cfg.get("board_timeout_s", 30)),
    )
    elfs = _find_elfs(act_cfg, root, only, build=options.get("build", True))
    build_dir.mkdir(parents=True, exist_ok=True)
    write_flash_stub(link, cfg, build_dir, sdram_base)

    show_display = bool(act_cfg.get("board_display", False))
    if show_display:
        # a new session starts without a failure
        display.write_fail(link, False)
    results: dict[str, bool | None] = {}
    for index, elf in enumerate(elfs):
        if show_display:
            display.write_display(link, display.encode_act(index + 1))
        passed, words, seconds = run_elf(link, cfg, elf, region)
        results[elf.stem] = passed
        if show_display and passed is not True:
            # the first red LED stays lit once any ELF has failed or
            # timed out
            display.write_fail(link, True)
        verdict = {True: "PASS", False: "FAIL", None: "TIMEOUT"}[passed]
        print(f"{elf.stem}: {verdict} ({words * 4} bytes, {seconds:.1f}s)")
    return results
