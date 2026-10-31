"""Read the loadable segments of an ACT4 ELF."""

import struct
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"


_PT_LOAD = 1


_ELF32_HEADER = struct.Struct("<16xHHIIIIIHHHHHH")


_ELF32_PHDR = struct.Struct("<IIIIIIII")


def load_segments(elf: Path) -> list[tuple[int, bytes]]:
    """Read the loadable segments of a little-endian 32-bit ELF.

    Parameters
    ----------
    elf : Path
        The ELF file.

    Returns
    -------
    list of (int, bytes)
        The physical address and the file contents of every `PT_LOAD`
        segment that has contents. Segments that only reserve zeroed
        space (`.bss`, the HTIF words) have none.
    """
    data = elf.read_bytes()
    if data[:4] != _ELF_MAGIC or data[4] != 1 or data[5] != 1:
        raise ValueError(f"{elf} is not a little-endian 32-bit ELF")
    fields = _ELF32_HEADER.unpack_from(data)
    phoff, phentsize, phnum = fields[4], fields[8], fields[9]
    segments: list[tuple[int, bytes]] = []
    for index in range(phnum):
        phdr = _ELF32_PHDR.unpack_from(data, phoff + index * phentsize)
        kind, offset, paddr, filesz = phdr[0], phdr[1], phdr[3], phdr[4]
        if kind == _PT_LOAD and filesz:
            segments.append((paddr, data[offset : offset + filesz]))
    return segments


def region_image(
    segments: list[tuple[int, bytes]], start: int, end: int
) -> bytes:
    """Build the flat image of the range `[start, end)` from segments.

    Parameters
    ----------
    segments : list of (int, bytes)
        The result of `load_segments`.
    start, end : int
        The first address of the range and the first address past it.

    Returns
    -------
    bytes
        The bytes of the range from `start` to the last byte any segment
        puts there, with zeros between segments; empty if no segment
        touches the range.
    """
    image = bytearray()
    for address, contents in segments:
        low, high = max(address, start), min(address + len(contents), end)
        if low >= high:
            continue
        if len(image) < high - start:
            image.extend(bytes(high - start - len(image)))
        image[low - start : high - start] = contents[
            low - address : high - address
        ]
    return bytes(image)
