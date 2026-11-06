"""Build the FLASH stub and the SDRAM image that the board loads."""

from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    flash_image,
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
) -> bool:
    """Write the stub into the FLASH over JTAG.

    The FLASH is written the way `quartus.rom_write_method` says: the
    memory editor or the JTAG loader of the FLASH.

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

    Returns
    -------
    bool
        True when the write restarted the core by itself (the JTAG
        loader), so the caller must not pulse `fromhost`.
    """
    stub = b"".join(
        w.to_bytes(4, "little") for w in flash_stub_words(sdram_base)
    )
    bin_path = build_dir / "flash_stub.bin"
    mif_path = build_dir / "flash_stub.mif"
    bin_path.write_bytes(stub)
    # The FLASH is addressed raw by the instruction bus, so the stub
    # sits at the word index of memory.rom_base, where the boot memory
    # jumps to (the same padding `compile` gives an image).
    pad_words = int(cfg["memory"]["rom_base"]) // 4
    bin_to_image.bin_to_mif(
        bin_path,
        mif_path,
        depth=pad_words + int(cfg["memory"]["rom_words"]),
        pad_words=pad_words,
    )
    return rom_writer.write_rom_configured(link, cfg, mif_path)


_HEADER_SIZE = flash_image.HEADER_SIZE


_JALR_X0_T0 = 0x00028067


def bank_stub_words(entry: int) -> list[int]:
    """Return the payload of the bank that sends the core to an ELF.

    Parameters
    ----------
    entry : int
        Address of the first instruction of the ELF.

    Returns
    -------
    list of int
        `lui t0, hi(entry)` and `jalr x0, lo(entry)(t0)`, with the
        carry of the sign of the low 12 bits in the high part.
    """
    high = (entry + 0x800) & _HIGH_20_BITS
    low = entry - high
    lui_t0 = high | (5 << 7) | _LUI_OPCODE
    jalr = _JALR_X0_T0 | ((low & _LOW_12_BITS) << 20)
    return [lui_t0, jalr]


def bank_image(
    cfg: dict[str, Any], code: bytes, entry: int, bank: str | None = None
) -> tuple[bytes, int]:
    """Wrap the code of an ELF in a valid bank of the FLASH.

    The boot memory of a platform with `flash.banks` jumps only to a bank
    whose header page is valid. The bank here holds a two-instruction
    payload that jumps to `entry`, and the code of the ELF follows at
    `entry`, outside the payload that the header checksums, so the ELF
    may use the whole FLASH instead of one bank.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses `flash.banks`.
    code : bytes
        The code of the ELF as it sits from `entry`.
    entry : int
        Address of the first byte of `code`, after the header page and
        the payload of the bank.
    bank : str, optional
        Name of the bank; the first one when omitted.

    Returns
    -------
    tuple of (bytes, int)
        The image and the address of its first byte.

    Raises
    ------
    ValueError
        The platform has no bank, the bank is unknown or `entry` falls
        inside the header page or the payload.
    """
    flash_cfg: dict[str, Any] = cfg.get("flash") or {}
    banks: list[dict[str, Any]] = flash_cfg.get("banks") or []
    if not banks:
        raise ValueError("the platform map has no flash.banks")
    chosen = [b for b in banks if bank in (None, str(b["name"]))]
    if not chosen:
        raise ValueError(f"the platform map has no bank {bank}")
    base = int(chosen[0]["base"])
    payload = b"".join(w.to_bytes(4, "little") for w in bank_stub_words(entry))
    head = flash_image.pack(payload, 1, int(chosen[0]["size"]))
    if entry < base + len(head):
        raise ValueError(
            f"the entry {entry:#x} is inside the header and the payload "
            f"of the bank at {base:#x}"
        )
    gap = bytes(entry - base - len(head))
    return head + gap + code, base
