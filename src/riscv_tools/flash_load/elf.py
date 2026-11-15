"""Lê os segmentos carregáveis de um ELF de 32 bits little-endian."""

import struct
from dataclasses import dataclass
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"
_CLASS_32 = 1
_LITTLE = 1
_PT_LOAD = 1
_HEADER = struct.Struct("<16xHHIIIIIHHHHHH")
_PROGRAM = struct.Struct("<IIIIIIII")


class ElfError(ValueError):
    """O arquivo não é um ELF de 32 bits little-endian utilizável."""


@dataclass(frozen=True)
class ElfSegment:
    """Um segmento carregável.

    Parameters
    ----------
    address : int
        O endereço de carga (`p_paddr`), onde o byte 0 do segmento vai.
    data : bytes
        Os `p_filesz` bytes do arquivo.
    """

    address: int
    data: bytes


def load_segments(path: Path) -> list[ElfSegment]:
    """Lê os segmentos `PT_LOAD` com conteúdo.

    Parameters
    ----------
    path : Path
        O ELF.

    Returns
    -------
    list of ElfSegment
        Os segmentos, por endereço de carga crescente.

    Raises
    ------
    ElfError
        Se o arquivo não é ELF32 little-endian ou está truncado.
    """
    blob = path.read_bytes()
    if blob[:4] != _ELF_MAGIC or len(blob) < _HEADER.size:
        raise ElfError(f"{path}: not an ELF file")
    if blob[4] != _CLASS_32 or blob[5] != _LITTLE:
        raise ElfError(f"{path}: only 32-bit little-endian ELF is read")
    fields = _HEADER.unpack_from(blob)
    phoff, phentsize, phnum = fields[4], fields[8], fields[9]
    found: list[ElfSegment] = []
    for index in range(phnum):
        start = phoff + index * phentsize
        if start + _PROGRAM.size > len(blob):
            raise ElfError(f"{path}: truncated program header table")
        kind, offset, _, paddr, filesz, *_ = _PROGRAM.unpack_from(blob, start)
        if kind == _PT_LOAD and filesz:
            if offset + filesz > len(blob):
                raise ElfError(f"{path}: segment beyond the end of the file")
            found.append(ElfSegment(paddr, blob[offset : offset + filesz]))
    return sorted(found, key=lambda s: s.address)


def flat_binary(segments: list[ElfSegment]) -> tuple[int, bytes]:
    """Junta os segmentos num binário contínuo, com zeros nos vãos.

    Parameters
    ----------
    segments : list of ElfSegment
        Os segmentos, por endereço crescente.

    Returns
    -------
    tuple of (int, bytes)
        O endereço do primeiro byte e o binário.

    Raises
    ------
    ElfError
        Se não há segmento.
    """
    if not segments:
        raise ElfError("the ELF has no loadable segment")
    first = segments[0].address
    image = bytearray()
    for segment in segments:
        image += bytes(segment.address - first - len(image))
        image += segment.data
    return first, bytes(image)
