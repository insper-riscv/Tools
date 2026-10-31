"""Write the images that the simulation and the board load."""

from pathlib import Path

from riscv_tools import bin_to_image
from riscv_tools.certify.segments import load_segments, region_image

_ADDRESS_SPACE = 1 << 32


_NOP = 0x00000013


_LUI_OPCODE = 0x37


_JALR_OPCODE = 0x67


_LOW_12_BITS = 0xFFF


_HIGH_20_BITS = 0xFFFFF000


def write_images(
    elf: Path, out_dir: Path, name: str, ram_base: int, boot_bytes: int
) -> dict[str, Path]:
    """Write the three hex images the simulation loads from an ELF.

    The code region (below `ram_base`) goes to the instruction memory
    and its first `boot_bytes` bytes also to the boot ROM; the data
    region (from `ram_base`) goes to the RAM. Every section of the ELF
    is loaded at the address it runs from.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF.
    out_dir : Path
        Where the `.bin` and `.hex` files are written.
    name : str
        Stem of the file names.
    ram_base : int
        First address of the RAM.
    boot_bytes : int
        Size in bytes of the boot ROM, at address 0.

    Returns
    -------
    dict of {str: Path}
        The hex files, under the keys `boot_hex_path`, `hex_path` and
        `ram_hex_path`.
    """
    segments = load_segments(elf)
    code = region_image(segments, 0, ram_base)
    data = region_image(segments, ram_base, _ADDRESS_SPACE)
    images = {
        "boot_hex_path": code[:boot_bytes],
        "hex_path": code,
        "ram_hex_path": data,
    }
    paths: dict[str, Path] = {}
    for key, image in images.items():
        suffix = key.removesuffix("_hex_path") if key != "hex_path" else "rom"
        bin_path = out_dir / f"{name}.{suffix}.bin"
        hex_path = out_dir / f"{name}.{suffix}.hex"
        # at least one word, so that the file is never empty
        bin_path.write_bytes(image or bytes(4))
        bin_to_image.bin_to_hex(bin_path, hex_path)
        paths[key] = hex_path
    return paths


def sdram_boot_words(sdram_base: int) -> list[int]:
    """Return the boot ROM that jumps to the SDRAM.

    The words are a nop, `lui x1, base` and `jalr x0, 0(x1)`. The core
    does not execute the first word after the reset, and the base has
    the low 12 bits clear (the SDRAM is 64 MB aligned).
    """
    if sdram_base & _LOW_12_BITS:
        raise ValueError(
            f"the SDRAM base {sdram_base:#x} is not 4 KiB aligned"
        )
    lui_x1 = (sdram_base & _HIGH_20_BITS) | (1 << 7) | _LUI_OPCODE
    jalr_x0 = (1 << 15) | _JALR_OPCODE
    return [_NOP, lui_x1, jalr_x0]


def write_sdram_images(
    elf: Path, out_dir: Path, name: str, sdram_base: int
) -> dict[str, Path]:
    """Write the two hex images the SDRAM simulation loads from an ELF.

    The ELF has everything in the SDRAM, loaded at the address it runs
    from. The image of the SDRAM chip starts at `sdram_base`; the boot
    ROM only jumps there.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF.
    out_dir : Path
        Where the files are written.
    name : str
        Stem of the file names.
    sdram_base : int
        First address of the SDRAM.

    Returns
    -------
    dict of {str: Path}
        The hex files, under the keys `boot_hex_path` and
        `sdram_hex_path`; `hex_path` is the boot image too, for the
        flash that the platform still has and nobody reads.
    """
    segments = load_segments(elf)
    sdram = region_image(segments, sdram_base, _ADDRESS_SPACE)
    boot = b"".join(
        word.to_bytes(4, "little") for word in sdram_boot_words(sdram_base)
    )
    paths: dict[str, Path] = {}
    for key, suffix, image in (
        ("boot_hex_path", "boot", boot),
        ("sdram_hex_path", "sdram", sdram),
    ):
        bin_path = out_dir / f"{name}.{suffix}.bin"
        hex_path = out_dir / f"{name}.{suffix}.hex"
        bin_path.write_bytes(image or bytes(4))
        bin_to_image.bin_to_hex(bin_path, hex_path)
        paths[key] = hex_path
    paths["hex_path"] = paths["boot_hex_path"]
    return paths


def write_flash_images(
    elf: Path, out_dir: Path, name: str, flash_base: int, sdram_base: int
) -> dict[str, Path]:
    """Write the three hex images of the FLASH platform from one ELF.

    The ELF has its code in the FLASH and its data in the SDRAM, each
    loaded at the address it runs from. The image of the FLASH starts at
    `flash_base`, the one of the SDRAM at `sdram_base`, and the boot ROM
    only jumps to the FLASH.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF.
    out_dir : Path
        Where the files are written.
    name : str
        Stem of the file names.
    flash_base : int
        First address of the FLASH.
    sdram_base : int
        First address of the SDRAM.

    Returns
    -------
    dict of {str: Path}
        The hex files, under the keys `boot_hex_path`, `hex_path` (the
        FLASH) and `sdram_hex_path`.
    """
    segments = load_segments(elf)
    flash = region_image(segments, flash_base, sdram_base)
    sdram = region_image(segments, sdram_base, _ADDRESS_SPACE)
    boot = b"".join(
        word.to_bytes(4, "little") for word in sdram_boot_words(flash_base)
    )
    paths: dict[str, Path] = {}
    for key, suffix, image in (
        ("boot_hex_path", "boot", boot),
        ("hex_path", "flash", flash),
        ("sdram_hex_path", "sdram", sdram),
    ):
        bin_path = out_dir / f"{name}.{suffix}.bin"
        hex_path = out_dir / f"{name}.{suffix}.hex"
        bin_path.write_bytes(image or bytes(4))
        bin_to_image.bin_to_hex(bin_path, hex_path)
        paths[key] = hex_path
    return paths
