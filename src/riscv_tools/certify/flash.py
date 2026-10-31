"""Build the FLASH stub and the SDRAM image that the board loads."""

from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    rom_writer,
)
from riscv_tools.certify.segments import load_segments, region_image
from riscv_tools.certify.symbols import elf_symbol
from riscv_tools.jtag import JtagLink

_FENCE_I = 0x0000100F


_JR_T0 = 0x00028067


_LUI_OPCODE = 0x37


_LOW_12_BITS = 0xFFF


_HIGH_20_BITS = 0xFFFFF000


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
    if sdram_base & _LOW_12_BITS:
        raise ValueError(
            f"the SDRAM base {sdram_base:#x} is not 4 KiB aligned"
        )
    lui_t0 = (sdram_base & _HIGH_20_BITS) | (5 << 7) | _LUI_OPCODE
    return [_FENCE_I, lui_t0, _JR_T0]


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
    segments = load_segments(elf)
    image = region_image(segments, sdram_base, tohost)
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
