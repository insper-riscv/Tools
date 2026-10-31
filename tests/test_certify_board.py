"""certify.board: the pieces that need no board."""

import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from riscv_tools.certify import board
from riscv_tools.jtag import JtagLink

SDRAM_BASE = 0x40000000


def _elf(segments: list[tuple[int, bytes]], symbols: dict[str, int]) -> bytes:
    """Build a 32-bit ELF with PT_LOAD segments and a symbol table."""
    phoff, phentsize, shentsize = 52, 32, 40
    names = b"\0" + b"".join(n.encode() + b"\0" for n in symbols)
    offsets: dict[str, int] = {}
    pos = 1
    for n in symbols:
        offsets[n] = pos
        pos += len(n) + 1
    symtab = bytes(16) + b"".join(
        struct.pack("<IIIBBH", offsets[n], v, 4, 0, 0, 1)
        for n, v in symbols.items()
    )
    body = bytearray()
    seg_offsets: list[int] = []
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
        struct.pack(
            "<IIIIIIII", 1, off, addr, addr, len(data), len(data), 7, 4
        )
        for (addr, data), off in zip(segments, seg_offsets, strict=True)
    )
    return bytes(header) + phdrs + bytes(body) + sections


def test_flash_stub_words() -> None:
    """Flash stub words."""
    fence_i, lui_t0, jr_t0 = board.flash_stub_words(SDRAM_BASE)
    assert fence_i == 0x0000100F
    assert lui_t0 == 0x400002B7  # lui t0, 0x40000
    assert jr_t0 == 0x00028067  # jalr x0, 0(t0)


def test_flash_stub_rejects_an_unaligned_base() -> None:
    """Flash stub rejects an unaligned base."""
    with pytest.raises(ValueError):
        board.flash_stub_words(SDRAM_BASE + 8)


def test_elf_symbol(tmp_path: Path) -> None:
    """Elf symbol."""
    elf = tmp_path / "t.elf"
    symbols = {"tohost": 0x400FFFE0, "main": 0x40000010}
    elf.write_bytes(_elf([(SDRAM_BASE, bytes(8))], symbols))
    assert board.elf_symbol(elf, "tohost") == 0x400FFFE0
    assert board.elf_symbol(elf, "main") == 0x40000010
    with pytest.raises(KeyError):
        board.elf_symbol(elf, "absent")


def test_image_words_stop_before_tohost(tmp_path: Path) -> None:
    """Image words stop before tohost."""
    code = bytes(range(8))
    htif = b"\xff" * 8
    elf = tmp_path / "t.elf"
    segments = [(SDRAM_BASE, code), (SDRAM_BASE + 0x20, htif)]
    elf.write_bytes(_elf(segments, {"tohost": SDRAM_BASE + 0x20}))
    # the HTIF segment starts at tohost and stays out of the image
    assert board.image_words(elf, SDRAM_BASE) == [0x03020100, 0x07060504]


def test_display_follows_each_elf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With board_display the display shows AC and the ELF number."""
    writes: list[int] = []
    verdicts: Iterator[bool | None] = iter([True, False, None])

    def write_display(_link: object, value: int) -> None:
        writes.append(value)

    def write_flash_stub(*_a: object, **_k: object) -> None:
        return None

    def run_elf(*_a: object, **_k: object) -> tuple[bool | None, int, float]:
        return (next(verdicts), 4, 0.1)

    def target_name(_cfg: object) -> str:
        return "t"

    def discover_elfs(directory: Path) -> list[Path]:
        return sorted(directory.glob("*.elf"))

    flags: list[bool] = []

    def write_fail(_link: object, failed: bool) -> bool:
        flags.append(failed)
        return failed

    monkeypatch.setattr(board.display, "write_display", write_display)
    monkeypatch.setattr(board.display, "write_fail", write_fail)
    monkeypatch.setattr(board, "write_flash_stub", write_flash_stub)
    monkeypatch.setattr(board, "run_elf", run_elf)
    elfs = tmp_path / "work" / "t" / "elfs"
    elfs.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (elfs / f"{name}.elf").write_bytes(b"")
    monkeypatch.setattr(board.certify_core, "target_name", target_name)
    monkeypatch.setattr(board.certify_core, "discover_elfs", discover_elfs)
    cfg: dict[str, Any] = {
        "act": {
            "sdram_base": "0x40000000",
            "target_config": "x",
            "vendor_dir": ".",
            "extensions": "I",
            "jobs": 1,
            "board_display": True,
        }
    }
    result = board.run_suite_on_board(
        cfg, tmp_path, tmp_path / "b", cast(JtagLink, None), build=False
    )
    assert result == {"a": True, "b": False, "c": None}
    assert writes == [0xAC0001, 0xAC0002, 0xAC0003]
    # cleared at the start, then set by the failed ELF and by the
    # timed-out one
    assert flags == [False, True, True]


def test_flash_stub_sits_at_rom_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flash stub sits at rom base."""
    written: list[Path] = []

    def write_rom(_link: object, _instances: object, mif: Path) -> None:
        written.append(mif)

    monkeypatch.setattr(board.rom_writer, "write_rom", write_rom)
    cfg = {
        "memory": {"rom_base": 0x800, "rom_words": 4},
        "quartus": {"rom_mem_instances": ["rom"]},
    }
    board.write_flash_stub(cast(JtagLink, None), cfg, tmp_path, SDRAM_BASE)
    lines = written[0].read_text().splitlines()
    data = {
        int(a, 16): int(v, 16)
        for a, v in (
            ln.strip().rstrip(";").split(":")
            for ln in lines
            if ":" in ln and "[" not in ln
        )
    }
    first = board.flash_stub_words(SDRAM_BASE)[0]
    assert data[0x800 // 4] == first
    assert data.get(0, 0) == 0
