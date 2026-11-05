"""The header of a program image in a FLASH bank, and its packing.

A bank starts with a header page of `HEADER_SIZE` bytes, followed by the
program (the payload). The header holds five little-endian words and
the rest of the page stays in the erased state (0xFF), so the update
routine writes the payload first and the header page last: a bank whose
header is not valid is a bank whose update did not finish.

| Offset | Word | Content |
| :--- | :--- | :--- |
| 0 | magic | `MAGIC` |
| 4 | size | bytes of the payload, a multiple of 4 |
| 8 | crc | CRC-32 (IEEE 802.3, as zlib) of the payload |
| 12 | version | version of the image, newer is larger |
| 16 | header_crc | CRC-32 of the first 16 bytes of the header |
"""

import struct
import zlib
from dataclasses import dataclass

MAGIC = 0x52564946
HEADER_SIZE = 256
SECTOR_SIZE = 4096
ERASED = 0xFF
_FIELDS = struct.Struct("<5I")
_BODY = struct.Struct("<4I")
_WORD = 4
_MAX_WORD = 0xFFFFFFFF


class ImageError(ValueError):
    """The image or the header breaks the format."""


@dataclass(frozen=True)
class ImageHeader:
    """The fields of a valid header.

    Attributes
    ----------
    size : int
        Bytes of the payload.
    crc : int
        CRC-32 of the payload.
    version : int
        Version of the image.
    """

    size: int
    crc: int
    version: int


def payload_crc(payload: bytes) -> int:
    """Compute the CRC-32 the header carries.

    Parameters
    ----------
    payload : bytes
        The payload, already padded to a whole number of words.

    Returns
    -------
    int
        The CRC-32 as an unsigned 32-bit number.
    """
    return zlib.crc32(payload) & _MAX_WORD


def pack(payload: bytes, version: int, bank_size: int | None = None) -> bytes:
    """Build the image of a bank: the header page, then the payload.

    Parameters
    ----------
    payload : bytes
        The program as the linker wrote it (a flat .bin).
    version : int
        Version of the image, from 0 to 2**32 - 2 (an erased word is
        not a version).
    bank_size : int, optional
        Size of the bank, in bytes; the image must fit in it.

    Returns
    -------
    bytes
        The header page followed by the payload, padded with 0xFF to a
        whole number of words.

    Raises
    ------
    ImageError
        If the payload is empty, the version is out of range or the
        image does not fit in the bank.
    """
    if not payload:
        raise ImageError("the payload is empty")
    if not 0 <= version < _MAX_WORD:
        raise ImageError(f"version {version} is out of range")
    padding = -len(payload) % _WORD
    payload += bytes([ERASED]) * padding
    if bank_size is not None and HEADER_SIZE + len(payload) > bank_size:
        raise ImageError(
            f"the image ({HEADER_SIZE + len(payload)} bytes) does not "
            f"fit in the bank ({bank_size} bytes)"
        )
    body = _BODY.pack(MAGIC, len(payload), payload_crc(payload), version)
    fields = body + struct.pack("<I", zlib.crc32(body) & _MAX_WORD)
    header = fields.ljust(HEADER_SIZE, bytes([ERASED]))
    return header + payload


def parse_header(image: bytes) -> ImageHeader:
    """Read and validate the header page of an image.

    Parameters
    ----------
    image : bytes
        The image, or at least its header page.

    Returns
    -------
    ImageHeader
        The fields of the header.

    Raises
    ------
    ImageError
        If the page is short, the magic is wrong, the header CRC does
        not match or the size is not a whole number of words.
    """
    if len(image) < _FIELDS.size:
        raise ImageError("the image is shorter than its header")
    magic, size, crc, version, header_crc = _FIELDS.unpack_from(image)
    if magic != MAGIC:
        raise ImageError(f"bad magic 0x{magic:08X}")
    if zlib.crc32(image[: _BODY.size]) & _MAX_WORD != header_crc:
        raise ImageError("the header CRC does not match")
    if size == 0 or size % _WORD:
        raise ImageError(f"bad payload size {size}")
    return ImageHeader(size=size, crc=crc, version=version)


def verify(image: bytes) -> ImageHeader:
    """Check a whole image against its header.

    Parameters
    ----------
    image : bytes
        The header page followed by the payload.

    Returns
    -------
    ImageHeader
        The fields of the header.

    Raises
    ------
    ImageError
        If the header is invalid, the payload is shorter than the
        header says, or its CRC does not match.
    """
    header = parse_header(image)
    payload = image[HEADER_SIZE : HEADER_SIZE + header.size]
    if len(image) < HEADER_SIZE + header.size:
        raise ImageError("the payload is shorter than the header says")
    if payload_crc(payload) != header.crc:
        raise ImageError("the payload CRC does not match")
    return header
