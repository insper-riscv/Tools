"""certify.board: the pieces that need no board."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from support import build_elf

from riscv_tools import rom_writer
from riscv_tools.certify import board, flash
from riscv_tools.certify.symbols import elf_symbol
from riscv_tools.jtag import JtagLink

SDRAM_BASE = 0x40000000


def test_flash_stub_words() -> None:
    """Flash stub words."""
    fence_i, lui_t0, jr_t0 = flash.flash_stub_words(SDRAM_BASE)
    assert fence_i == 0x0000100F
    assert lui_t0 == 0x400002B7  # lui t0, 0x40000
    assert jr_t0 == 0x00028067  # jalr x0, 0(t0)


def test_flash_stub_rejects_an_unaligned_base() -> None:
    """Flash stub rejects an unaligned base."""
    with pytest.raises(ValueError):
        flash.flash_stub_words(SDRAM_BASE + 8)


def test_elf_symbol(tmp_path: Path) -> None:
    """Elf symbol."""
    elf = tmp_path / "t.elf"
    symbols = {"tohost": 0x400FFFE0, "main": 0x40000010}
    elf.write_bytes(build_elf([(SDRAM_BASE, bytes(8))], symbols))
    assert elf_symbol(elf, "tohost") == 0x400FFFE0
    assert elf_symbol(elf, "main") == 0x40000010
    with pytest.raises(KeyError):
        elf_symbol(elf, "absent")


def test_image_words_stop_before_tohost(tmp_path: Path) -> None:
    """Image words stop before tohost."""
    code = bytes(range(8))
    htif = b"\xff" * 8
    elf = tmp_path / "t.elf"
    segments = [(SDRAM_BASE, code), (SDRAM_BASE + 0x20, htif)]
    elf.write_bytes(build_elf(segments, {"tohost": SDRAM_BASE + 0x20}))
    # the HTIF segment starts at tohost and stays out of the image
    assert flash.image_words(elf, SDRAM_BASE) == [0x03020100, 0x07060504]


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

    monkeypatch.setattr(rom_writer, "write_rom", write_rom)
    cfg = {
        "memory": {"rom_base": 0x800, "rom_words": 4},
        "quartus": {"rom_mem_instances": ["rom"]},
    }
    flash.write_flash_stub(cast(JtagLink, None), cfg, tmp_path, SDRAM_BASE)
    lines = written[0].read_text().splitlines()
    data = {
        int(a, 16): int(v, 16)
        for a, v in (
            ln.strip().rstrip(";").split(":")
            for ln in lines
            if ":" in ln and "[" not in ln
        )
    }
    first = flash.flash_stub_words(SDRAM_BASE)[0]
    assert data[0x800 // 4] == first
    assert data.get(0, 0) == 0
