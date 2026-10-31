"""certify: the images the simulation loads from an ACT4 ELF."""

from pathlib import Path

import pytest
from support import build_elf

from riscv_tools.certify import core

SDRAM_BASE = 0x40000000


def test_sdram_boot_words_jump_to_the_base():
    """Sdram boot words jump to the base."""
    nop, lui_x1, jalr_x0 = core.sdram_boot_words(SDRAM_BASE)
    assert nop == 0x00000013
    assert lui_x1 == 0x400000B7  # lui x1, 0x40000
    assert jalr_x0 == 0x00008067  # jalr x0, 0(x1)


def test_sdram_boot_words_reject_an_unaligned_base():
    """Sdram boot words reject an unaligned base."""
    with pytest.raises(ValueError):
        core.sdram_boot_words(SDRAM_BASE + 4)


def test_write_sdram_images_joins_the_segments_from_the_base(
    tmp_path: Path,
) -> None:
    """Write sdram images joins the segments from the base."""
    code = bytes(range(16))
    data = b"\xaa\xbb\xcc\xdd"
    elf = tmp_path / "t.elf"
    elf.write_bytes(build_elf([(SDRAM_BASE, code), (SDRAM_BASE + 0x20, data)]))
    paths = core.write_sdram_images(elf, tmp_path, "t", SDRAM_BASE)
    assert set(paths) == {"boot_hex_path", "sdram_hex_path", "hex_path"}
    words = paths["sdram_hex_path"].read_text().lower().split()
    assert len(words) == 9  # 0x24 bytes, the gap filled with zeros
    assert words[0] == "03020100"
    assert words[4:8] == ["00000000"] * 4
    assert words[8] == "ddccbbaa"
    boot = paths["boot_hex_path"].read_text().lower().split()
    assert boot == ["00000013", "400000b7", "00008067"]
    assert paths["hex_path"] == paths["boot_hex_path"]
