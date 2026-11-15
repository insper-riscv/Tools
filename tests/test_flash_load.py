"""Tests of the host side of the FLASH in the SDRAM."""

import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from support import build_elf, check, check_equal, check_in

from riscv_tools import (
    flash_image,
    flash_load,
    ram_dump,
    ram_load,
    ram_target,
    ram_zero,
    rom_writer,
    sdram_debug,
)
from riscv_tools.jtag import JtagLink
from riscv_tools.ram_target import SdramDebugRam
from riscv_tools.sdram_debug import core as sdram_core
from riscv_tools.sdram_debug import stream as sdram_stream
from riscv_tools.sdram_windows import Window

LINK = JtagLink(hardware_name="cable", device_name="device")
FLASH = Window("FLASH", 0x1000, 0x1FFF000, 0x1000)
RAM = Window("RAM", 0x40000000, 0x2000000, 0x2000000)
BURST = 32


class Board:
    """Stands for the board: answers the two scripts like the hardware.

    The capability word, the hold level, the CRC and the burst follow
    the contract of `sdram_debug.md`.
    """

    def __init__(self, info: int = 0x30000 | (BURST << 8)) -> None:
        """Start with an empty chip."""
        self.info = info
        self.memory: dict[int, int] = {}
        self.hold = False
        self.holds: list[bool] = []
        self.bursts: list[int] = []
        self.crc_fault = False
        self.calls: list[tuple[Any, ...]] = []

    def run(self, _link: JtagLink, script: str, *args: Any) -> Any:
        """Record the call and answer it."""
        self.calls.append((script, *args))
        stdout = getattr(self, f"_{args[0]}")(*args[1:])
        return type("Completed", (), {"stdout": stdout})()

    def _info(self) -> str:
        return f"INFO={self.info:08x}"

    def _hold(self, value: int) -> str:
        self.hold = bool(value)
        self.holds.append(self.hold)
        return "OK"

    def _crc(self, first: int, count: int) -> str:
        if self.crc_fault:
            return "CRC=00000000"
        data = b"".join(
            struct.pack("<I", self.memory.get(first + i, 0))
            for i in range(count)
        )
        return f"CRC={zlib.crc32(data):08x}"

    def _streamwrite(self, first: int, path: Path) -> str:
        check(self.hold, "the FLASH is written with the core held")
        self.bursts.append(first)
        words = [int(t, 16) for t in Path(path).read_text("utf-8").split()]
        check(len(words) % BURST == 0, "a burst is whole")
        self.memory |= {first + i: w for i, w in enumerate(words)}
        return f"OK {len(words)}"

    def _streamread(self, first: int, count: int, path: Path) -> str:
        words = [self.memory.get(first + i, 0) for i in range(count)]
        Path(path).write_text("".join(f"{w:08x}\n" for w in words), "utf-8")
        return f"OK {count}"

    def _load(self, first: int, path: Path) -> str:
        words = [int(t, 16) for t in Path(path).read_text("utf-8").split()]
        self.memory |= {first + i: w for i, w in enumerate(words)}
        return f"OK {len(words)}"

    def _read(self, first: int, count: int) -> str:
        words = (self.memory.get(first + i, 0) for i in range(count))
        return "WORDS=" + " ".join(str(w) for w in words)

    def _write(self, first: int, value: int, _be: int = 0xF) -> str:
        self.memory[first] = value
        return "OK"

    def _fill(self, first: int, count: int, value: int) -> str:
        self.memory |= {first + i: value for i in range(count)}
        return "OK"


@pytest.fixture
def board(monkeypatch: pytest.MonkeyPatch) -> Board:
    """Replace the quartus scripts by the model of the board."""
    model = Board()
    monkeypatch.setattr(sdram_core, "run_tcl", model.run)
    monkeypatch.setattr(sdram_stream, "run_tcl", model.run)
    return model


def _image(size: int) -> bytes:
    """Give a packed image of the given payload size."""
    return flash_image.pack(bytes(range(256)) * (size // 256), 7)


def test_the_capability_word_tells_what_the_bitstream_has() -> None:
    """Bits 15:8 are the burst, bit 16 the hold and bit 17 the CRC."""
    caps = sdram_debug.decode_capabilities(0x00030000 | (32 << 8))
    check_equal((caps.stream_words, caps.hold, caps.crc), (32, True, True))
    check(caps.can_load_flash)
    none = sdram_debug.decode_capabilities(0)
    check_equal((none.stream_words, none.hold, none.crc), (0, False, False))
    check(not none.can_load_flash)


def test_the_flash_is_written_by_burst_and_checked_by_the_crc(
    board: Board,
) -> None:
    """The image lands in the window, then the core is released."""
    image = _image(4096)
    crc = flash_load.load_flash(
        LINK, FLASH, flash_load.FlashImage(0x1000, image, 256)
    )
    check_equal(crc, zlib.crc32(image))
    words = len(image) // 4
    stored = [board.memory[0x1000 // 4 + i] for i in range(words)]
    check_equal(struct.pack(f"<{words}I", *stored), image)
    check_equal(board.holds, [True, False])
    check_equal(board.hold, False)


def test_the_header_of_a_bank_is_written_last(board: Board) -> None:
    """An interrupted write leaves a bank the BOOT does not validate."""
    image = _image(4096)
    flash_load.load_flash(
        LINK, FLASH, flash_load.FlashImage(0x1000, image, 256)
    )
    check_equal(board.bursts, [0x1000 // 4 + 64, 0x1000 // 4])


def test_a_tail_that_is_not_a_burst_goes_word_by_word(board: Board) -> None:
    """The write never goes past the end of the image."""
    data = bytes(range(200))
    flash_load.load_flash(LINK, FLASH, flash_load.FlashImage(0x1000, data))
    check_equal(len([c for c in board.calls if c[1] == "streamwrite"]), 1)
    check_equal(board.memory.get(0x1000 // 4 + 50), None)
    loads = [c[:3] for c in board.calls if c[1] == "load"]
    check_equal(loads, [("sdram_dbg.tcl", "load", 0x1000 // 4 + 32)])


def test_a_bitstream_without_hold_is_refused(board: Board) -> None:
    """The FLASH is never written while the core can run."""
    board.info = (BURST << 8) | 0x20000
    with pytest.raises(flash_load.FlashLoadError, match="no hold and CRC"):
        flash_load.load_flash(
            LINK, FLASH, flash_load.FlashImage(0x1000, b"\0" * 16)
        )
    check_equal(board.holds, [])
    check_equal(board.memory, {})


def test_a_crc_that_differs_is_an_error_and_the_core_is_released(
    board: Board,
) -> None:
    """The BOOT validates the banks and picks the intact one."""
    board.crc_fault = True
    with pytest.raises(flash_load.FlashLoadError, match="CRC-32 of the board"):
        flash_load.load_flash(
            LINK, FLASH, flash_load.FlashImage(0x1000, b"\1" * 64)
        )
    check_equal(board.holds, [True, False])


@pytest.mark.parametrize(
    ("address", "size", "message"),
    [
        (0x10, 64, "outside the FLASH"),
        (0x1002, 64, "words"),
        (0x1FFF000 + 0x1000 - 32, 64, "outside the FLASH"),
        (0x1000, 0, "empty"),
    ],
)
def test_a_bad_request_never_touches_the_board(
    board: Board, address: int, size: int, message: str
) -> None:
    """The window and the alignment are checked first."""
    with pytest.raises(flash_load.FlashLoadError, match=message):
        flash_load.load_flash(
            LINK, FLASH, flash_load.FlashImage(address, b"\0" * size)
        )
    check_equal(board.calls, [])


def test_the_dump_of_a_region_reads_its_window(board: Board) -> None:
    """The RAM is at the offset of its window, in order of address."""
    base = RAM.offset // 4
    board.memory |= {base + 4 + i: 0x1000 + i for i in range(40)}
    data = ram_dump.dump_region(LINK, RAM, RAM.base + 16, 160)
    check_equal(struct.unpack("<40I", data), tuple(range(0x1000, 0x1028)))
    heads = [c[:4] for c in board.calls]
    check_in(("sdram_stream.tcl", "streamread", base + 4, 32), heads)
    with pytest.raises(ValueError, match="outside RAM"):
        ram_dump.dump_region(LINK, RAM, RAM.end - 4, 8)


def test_the_dump_is_saved_as_bytes_or_as_mif(tmp_path: Path) -> None:
    """`.bin` is the raw bytes; anything else is a `.mif`."""
    data = struct.pack("<2I", 1, 0xDEADBEEF)
    ram_dump.save_region(tmp_path / "x.bin", RAM, RAM.base + 8, data)
    check_equal((tmp_path / "x.bin").read_bytes(), data)
    ram_dump.save_region(tmp_path / "x.mif", RAM, RAM.base + 8, data)
    text = (tmp_path / "x.mif").read_text()
    check_in("  2 : 00000001;", text)
    check_in("  3 : DEADBEEF;", text)


def test_the_ram_target_counts_from_the_window_of_the_ram(
    board: Board,
) -> None:
    """Word offsets of the RAM are added to the offset of its window."""
    cfg = {
        "quartus": {"ram_backend": "sdram_debug"},
        "memory": {
            "sdram_windows": {
                "RAM": {"base": RAM.base, "size": RAM.size, "offset": "32M"}
            }
        },
    }
    target = ram_target.target_from_config(cfg)
    check_equal(target, SdramDebugRam(32 * 1024 * 1024 // 4))
    ram_target.write_word(LINK, target, 3, 9)
    check_equal(board.memory, {32 * 1024 * 1024 // 4 + 3: 9})
    check_equal(ram_target.read_words(LINK, target, 3, 1), [9])
    ram_zero.zero_ram(LINK, target, 4)
    check_equal(board.memory[32 * 1024 * 1024 // 4 + 3], 0)


def test_load_ram_counts_from_the_window_of_the_ram(board: Board) -> None:
    """`load-ram` keeps working in a split chip."""
    segment = ram_load.Segment("binary", RAM.base + 8, struct.pack("<I", 5))
    options = ram_load.LoadOptions(chip_words=RAM.offset // 4)
    ram_load.load_ram(LINK, [segment], RAM.base, None, options)
    check_equal(board.memory, {RAM.offset // 4 + 2: 5})


def test_the_rom_method_sdram_debug_writes_the_flash_window(
    board: Board, tmp_path: Path
) -> None:
    """`quartus.rom_write_method: sdram_debug` loads the `.mif`."""
    mif = tmp_path / "flash.mif"
    lines = [f"  {0x1000 // 4 + i:X} : {i + 1:08X};" for i in range(40)]
    mif.write_text(
        "WIDTH=32;\nDEPTH=1024;\nADDRESS_RADIX=HEX;\nDATA_RADIX=HEX;\n"
        "CONTENT BEGIN\n" + "\n".join(lines) + "\nEND;\n"
    )
    cfg = {
        "quartus": {"rom_write_method": "sdram_debug"},
        "memory": {
            "sdram_windows": {
                "FLASH": {"base": 0x1000, "size": 0x1FFF000, "offset": 0x1000}
            }
        },
    }
    check_equal(rom_writer.method_from_config(cfg), "sdram_debug")
    restarted = rom_writer.write_rom_configured(LINK, cfg, mif)
    check(restarted, "the release of the hold restarts the core")
    check_equal(board.memory[0x1000 // 4 + 39], 40)
    check_equal(board.holds, [True, False])


def test_the_elf_segments_become_a_bank_image(tmp_path: Path) -> None:
    """The program of a bank is linked after the header page."""
    path = tmp_path / "app.elf"
    path.write_bytes(build_elf([(0x1100, bytes(range(1, 65)))]))
    segments = flash_load.load_segments(path)
    check_equal([s.address for s in segments], [0x1100])
    first, payload = flash_load.flat_binary(segments)
    check_equal((first, payload), (0x1100, bytes(range(1, 65))))
    bad = tmp_path / "bad.elf"
    bad.write_bytes(b"not an elf")
    with pytest.raises(flash_load.ElfError):
        flash_load.load_segments(bad)
