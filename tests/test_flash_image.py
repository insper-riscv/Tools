"""Tests for the FLASH bank image: header, packing and sending."""

import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from support import MEMORY_TEXT, check, check_equal, check_in

from riscv_tools import cli, flash_image
from riscv_tools.flash_image import send as send_module
from riscv_tools.jtag import JtagLink

LINK = JtagLink(hardware_name="cable", device_name="device")
PROGRAM = bytes(range(1, 11))


def test_pack_puts_the_header_page_before_the_program() -> None:
    """The image is the header page, then the padded program."""
    image = flash_image.pack(PROGRAM, 7)
    payload = PROGRAM + b"\xff\xff"
    check_equal(len(image), flash_image.HEADER_SIZE + len(payload))
    check_equal(image[flash_image.HEADER_SIZE :], payload)
    magic, size, crc, version, header_crc = struct.unpack_from("<5I", image)
    check_equal(magic, flash_image.MAGIC)
    check_equal(size, len(payload))
    check_equal(crc, zlib.crc32(payload))
    check_equal(version, 7)
    check_equal(header_crc, zlib.crc32(image[:16]))
    check_equal(image[20 : flash_image.HEADER_SIZE], b"\xff" * 236)


def test_a_packed_image_verifies() -> None:
    """Verify returns the fields that pack wrote."""
    header = flash_image.verify(flash_image.pack(PROGRAM, 3))
    check_equal(header.version, 3)
    check_equal(header.size, 12)


def test_an_erased_bank_has_no_valid_header() -> None:
    """An erased page (all ones) is not an image."""
    with pytest.raises(flash_image.ImageError, match="bad magic"):
        flash_image.parse_header(b"\xff" * flash_image.HEADER_SIZE)


@pytest.mark.parametrize(
    ("offset", "message"),
    [
        (0, "bad magic"),
        (4, "header CRC"),
        (12, "header CRC"),
        (16, "header CRC"),
        (flash_image.HEADER_SIZE + 2, "payload CRC"),
    ],
)
def test_a_damaged_image_is_rejected(offset: int, message: str) -> None:
    """A flipped bit in the header or in the payload is caught."""
    image = bytearray(flash_image.pack(PROGRAM, 1))
    image[offset] ^= 0x01
    with pytest.raises(flash_image.ImageError, match=message):
        flash_image.verify(bytes(image))


def test_a_cut_image_is_rejected() -> None:
    """An image shorter than its header says is rejected."""
    image = flash_image.pack(PROGRAM, 1)
    with pytest.raises(flash_image.ImageError, match="shorter"):
        flash_image.verify(image[:-4])
    with pytest.raises(flash_image.ImageError, match="shorter"):
        flash_image.parse_header(b"\x00")


def test_pack_refuses_what_does_not_fit_or_make_sense() -> None:
    """Empty payloads, bad versions and oversized images fail."""
    with pytest.raises(flash_image.ImageError, match="empty"):
        flash_image.pack(b"", 0)
    with pytest.raises(flash_image.ImageError, match="version"):
        flash_image.pack(PROGRAM, 0xFFFFFFFF)
    with pytest.raises(flash_image.ImageError, match="version"):
        flash_image.pack(PROGRAM, -1)
    flash_image.pack(b"\x00" * 4, 0, bank_size=260)
    with pytest.raises(flash_image.ImageError, match="does not fit"):
        flash_image.pack(b"\x00" * 5, 0, bank_size=260)


def test_send_gives_the_image_in_order_in_chunks() -> None:
    """The reader receives every byte once, in order."""
    image = flash_image.pack(b"\x01" * 40000, 1)
    sent: list[bytes] = []

    def reader(
        link: JtagLink, _on_bytes: Any, seconds: float, send: bytes
    ) -> bytes:
        check_equal(link, LINK)
        check(seconds > 0)
        check(len(send) <= send_module.CHUNK)
        sent.append(send)
        return b""

    count = flash_image.send_image(LINK, image, print, reader)
    check_equal(count, len(image))
    check_equal(b"".join(sent), image)
    check_equal(len(sent), 3)


def test_the_command_packs_verifies_and_checks_the_bank(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command writes an image, checks it and honours the bank."""
    (tmp_path / "prog.bin").write_bytes(PROGRAM)
    (tmp_path / "platform.yaml").write_text(
        MEMORY_TEXT + "flash:\n  region: FLASH\n  banks:\n"
        "    - {name: A, base: 0x1000, size: 4K}\n"
    )
    root = str(tmp_path)
    out = str(tmp_path / "img.bin")
    prog = str(tmp_path / "prog.bin")
    base = ["riscv-tools", "--root", root, "flash-image"]
    for argv in (
        [
            *base,
            *("pack", prog, "--output", out, "--version", "2"),
            *("--platform", "platform.yaml", "--bank", "A"),
        ],
        [*base, "verify", out],
    ):
        monkeypatch.setattr("sys.argv", argv)
        cli.main()
    check_in("CRC 0x", capsys.readouterr().out)
    for argv in (
        [*base, "pack", prog],
        [*base, "pack", prog, "--output", out, "--bank", "A"],
        [
            *base,
            *("pack", prog, "--output", out),
            *("--platform", "platform.yaml", "--bank", "Z"),
        ],
        [*base, "send", out],
    ):
        monkeypatch.setattr("sys.argv", argv)
        with pytest.raises(SystemExit) as raised:
            cli.main()
        check_equal(raised.value.code, 1)


BANKS_CONFIG: dict[str, Any] = {
    "memory": {"rom_base": 0x1000, "rom_words": 64512},
    "flash": {
        "banks": [
            {"name": "A", "base": 0x1000, "size": 0x1F000},
            {"name": "B", "base": 0x20000, "size": 0x20000},
        ]
    },
    "flash_image": {"bank": "B", "version": 4},
}


def _compile_bin(tmp_path: Path) -> Path:
    path = tmp_path / "t.bin"
    path.write_bytes(PROGRAM)
    return path


def test_a_config_without_flash_image_leaves_the_binary_alone(
    tmp_path: Path,
) -> None:
    """Platforms with a single image keep the raw binary."""
    bin_ = _compile_bin(tmp_path)
    config = {k: v for k, v in BANKS_CONFIG.items() if k != "flash_image"}
    got = flash_image.image_for_config(config, tmp_path, "t", bin_)
    check_equal(got, (bin_, None))


def test_flash_image_packs_the_binary_for_the_named_bank(
    tmp_path: Path,
) -> None:
    """The packed image verifies and starts at the base of the bank."""
    packed, base = flash_image.image_for_config(
        BANKS_CONFIG, tmp_path, "t", _compile_bin(tmp_path)
    )
    check_equal(base, 0x20000)
    header = flash_image.verify(packed.read_bytes())
    check_equal(header.version, 4)


def test_flash_image_rejects_a_bank_the_map_lacks(tmp_path: Path) -> None:
    """A wrong bank name is an error, not a silent raw image."""
    config = {**BANKS_CONFIG, "flash_image": {"bank": "C"}}
    with pytest.raises(flash_image.ImageError):
        flash_image.image_for_config(
            config, tmp_path, "t", _compile_bin(tmp_path)
        )
