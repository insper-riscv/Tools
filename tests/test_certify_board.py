"""certify.board: the pieces that need no board."""

import struct

import pytest

from riscv_tools.certify import board

SDRAM_BASE = 0x40000000


def _elf(segments, symbols):
    """Build a 32-bit ELF with PT_LOAD segments and a symbol table."""
    phoff, phentsize, shentsize = 52, 32, 40
    names = b"\0" + b"".join(n.encode() + b"\0" for n in symbols)
    offsets, pos = {}, 1
    for n in symbols:
        offsets[n] = pos
        pos += len(n) + 1
    symtab = bytes(16) + b"".join(
        struct.pack("<IIIBBH", offsets[n], v, 4, 0, 0, 1) for n, v in symbols.items()
    )
    body = bytearray()
    seg_offsets = []
    base = phoff + phentsize * len(segments)
    for _, data in segments:
        seg_offsets.append(base + len(body))
        body += data
    symtab_off = base + len(body)
    body += symtab
    names_off = base + len(body)
    body += names
    shoff = base + len(body)
    sections = bytes(shentsize)
    sections += struct.pack(
        "<IIIIIIIIII", 0, 2, 0, 0, symtab_off, len(symtab), 2, 0, 4, 16
    )
    sections += struct.pack(
        "<IIIIIIIIII", 0, 3, 0, 0, names_off, len(names), 0, 0, 1, 0
    )
    header = bytearray(52)
    header[:4] = b"\x7fELF"
    header[4], header[5] = 1, 1
    struct.pack_into(
        "<HHIIIIIHHHHHH",
        header,
        16,
        2,
        0xF3,
        1,
        0,
        phoff,
        shoff,
        0,
        52,
        phentsize,
        len(segments),
        shentsize,
        3,
        0,
    )
    phdrs = b"".join(
        struct.pack("<IIIIIIII", 1, off, addr, addr, len(data), len(data), 7, 4)
        for (addr, data), off in zip(segments, seg_offsets, strict=True)
    )
    return bytes(header) + phdrs + bytes(body) + sections


def test_flash_stub_words():
    fence_i, lui_t0, jr_t0 = board.flash_stub_words(SDRAM_BASE)
    assert fence_i == 0x0000100F
    assert lui_t0 == 0x400002B7  # lui t0, 0x40000
    assert jr_t0 == 0x00028067  # jalr x0, 0(t0)


def test_flash_stub_rejects_an_unaligned_base():
    with pytest.raises(ValueError):
        board.flash_stub_words(SDRAM_BASE + 8)


def test_elf_symbol(tmp_path):
    elf = tmp_path / "t.elf"
    symbols = {"tohost": 0x400FFFE0, "main": 0x40000010}
    elf.write_bytes(_elf([(SDRAM_BASE, bytes(8))], symbols))
    assert board.elf_symbol(elf, "tohost") == 0x400FFFE0
    assert board.elf_symbol(elf, "main") == 0x40000010
    with pytest.raises(KeyError):
        board.elf_symbol(elf, "absent")


def test_image_words_stop_before_tohost(tmp_path):
    code = bytes(range(8))
    htif = b"\xff" * 8
    elf = tmp_path / "t.elf"
    segments = [(SDRAM_BASE, code), (SDRAM_BASE + 0x20, htif)]
    elf.write_bytes(_elf(segments, {"tohost": SDRAM_BASE + 0x20}))
    # the HTIF segment starts at tohost and stays out of the image
    assert board.image_words(elf, SDRAM_BASE) == [0x03020100, 0x07060504]
