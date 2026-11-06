"""certify.board: the pieces that need no board."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from support import build_elf, check_equal

from riscv_tools import flash_image, rom_writer
from riscv_tools.certify import board, flash
from riscv_tools.certify.symbols import elf_symbol
from riscv_tools.jtag import JtagLink

SDRAM_BASE = 0x40000000


def test_flash_stub_words() -> None:
    """Flash stub words."""
    fence_i, lui_t0, jr_t0 = flash.flash_stub_words(SDRAM_BASE)
    check_equal(fence_i, 0x0000100F)
    check_equal(lui_t0, 0x400002B7)  # lui t0, 0x40000
    check_equal(jr_t0, 0x00028067)  # jalr x0, 0(t0)


def test_flash_stub_rejects_an_unaligned_base() -> None:
    """Flash stub rejects an unaligned base."""
    with pytest.raises(ValueError):
        flash.flash_stub_words(SDRAM_BASE + 8)


def test_elf_symbol(tmp_path: Path) -> None:
    """Elf symbol."""
    elf = tmp_path / "t.elf"
    symbols = {"tohost": 0x400FFFE0, "main": 0x40000010}
    elf.write_bytes(build_elf([(SDRAM_BASE, bytes(8))], symbols))
    check_equal(elf_symbol(elf, "tohost"), 0x400FFFE0)
    check_equal(elf_symbol(elf, "main"), 0x40000010)
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
    check_equal(flash.image_words(elf, SDRAM_BASE), [0x03020100, 0x07060504])


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
    check_equal(result, {"a": True, "b": False, "c": None})
    check_equal(writes, [0xAC0001, 0xAC0002, 0xAC0003])
    # cleared at the start, then set by the failed ELF and by the
    # timed-out one
    check_equal(flags, [False, True, True])


def test_flash_stub_sits_at_rom_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flash stub sits at rom base."""
    written: list[Path] = []

    def write_rom(_link: object, _cfg: object, mif: Path) -> bool:
        written.append(mif)
        return False

    monkeypatch.setattr(rom_writer, "write_rom_configured", write_rom)
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
    check_equal(data[0x800 // 4], first)
    check_equal(data.get(0, 0), 0)


def _written_as(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, method: str
) -> list[str]:
    """Run an ELF from the FLASH on a fake board; list what it did."""
    calls: list[str] = []

    def write_rom(_link: object, cfg: dict[str, Any], _mif: Path) -> bool:
        calls.append(f"write:{cfg['quartus']['rom_write_method']}")
        return cfg["quartus"]["rom_write_method"] == "jtag_loader"

    def pulse(_link: object, _cfg: object) -> None:
        calls.append("pulse")

    monkeypatch.setattr(rom_writer, "write_rom_configured", write_rom)
    monkeypatch.setattr(board.htif, "pulse_fromhost_configured", pulse)

    def nothing(*_a: object) -> None:
        return None

    def done(*_a: object) -> list[int]:
        return [1]

    monkeypatch.setattr(board.sdram_debug, "fill", nothing)
    monkeypatch.setattr(board.sdram_debug, "load_words", nothing)
    monkeypatch.setattr(board.sdram_debug, "read_words", done)
    elf = tmp_path / "t.elf"
    segments = [(0x1000, bytes(8)), (SDRAM_BASE + 0x20, b"\xff" * 8)]
    elf.write_bytes(build_elf(segments, {"tohost": SDRAM_BASE + 0x20}))
    cfg: dict[str, Any] = {
        "quartus": {"rom_write_method": method},
        "act": {"flash_base": "0x1000", "flash_words": 16},
    }
    region = board.SdramRegion(SDRAM_BASE, 16, 1.0)
    board.run_elf_flash(cast(JtagLink, None), cfg, elf, region, tmp_path)
    return calls


def test_run_elf_flash_follows_the_write_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The memory editor needs the pulse of fromhost, the loader not."""
    check_equal(
        _written_as(monkeypatch, tmp_path, "mem_edit"),
        ["write:mem_edit", "pulse"],
    )
    check_equal(
        _written_as(monkeypatch, tmp_path, "jtag_loader"),
        ["write:jtag_loader"],
    )


def test_bank_stub_words_jump_to_the_entry() -> None:
    """The payload of the bank is lui t0 and jalr x0 to the entry."""
    check_equal(flash.bank_stub_words(0x1200), [0x000012B7, 0x20028067])
    # a low part with the sign bit set is carried into the high part
    check_equal(flash.bank_stub_words(0x1800), [0x000022B7, 0x80028067])


def test_bank_image_wraps_the_code_in_a_valid_bank() -> None:
    """The image starts at the bank, with the code at the entry."""
    cfg = {
        "flash": {"banks": [{"name": "A", "base": 0x1000, "size": 0x1F000}]}
    }
    image, base = flash.bank_image(cfg, b"\xaa" * 8, 0x1200)
    check_equal(base, 0x1000)
    check_equal(len(image), 0x200 + 8)
    check_equal(image[0x200:], b"\xaa" * 8)
    header = flash_image.parse_header(image[:0x100])
    check_equal(header.size, 8)
    check_equal(
        image[0x100:0x108],
        b"".join(
            w.to_bytes(4, "little") for w in flash.bank_stub_words(0x1200)
        ),
    )


def test_bank_image_rejects_an_entry_inside_the_header() -> None:
    """An entry before the end of the payload is an error."""
    cfg = {
        "flash": {"banks": [{"name": "A", "base": 0x1000, "size": 0x1F000}]}
    }
    with pytest.raises(ValueError):
        flash.bank_image(cfg, b"\0" * 4, 0x1100)
    with pytest.raises(ValueError):
        flash.bank_image(cfg, b"\0" * 4, 0x1200, "Z")
    with pytest.raises(ValueError):
        flash.bank_image({}, b"\0" * 4, 0x1200)


def testflash_code_of_a_bank_starts_at_the_storage_origin(
    tmp_path: Path,
) -> None:
    """The bank sits at its address inside the raw-addressed storage."""
    elf = tmp_path / "t.elf"
    code = bytes(range(16))
    segments = [(0x1200, code), (SDRAM_BASE + 0x20, b"\xff" * 8)]
    elf.write_bytes(build_elf(segments, {"tohost": SDRAM_BASE + 0x20}))
    cfg: dict[str, Any] = {
        "act": {"flash_bank": "A", "flash_entry": "0x1200"},
        "memory": {"rom_origin": 0},
        "flash": {"banks": [{"name": "A", "base": 0x1000, "size": 0x1F000}]},
    }
    image = board.flash_code(cfg, elf, SDRAM_BASE)
    check_equal(len(image), 0x1200 + 16)
    check_equal(image[0x1200:], code)
    check_equal(image[:0x1000], bytes(0x1000))
