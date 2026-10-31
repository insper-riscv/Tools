"""Read a symbol address from the symbol table of a 32-bit ELF."""

import struct
from collections.abc import Iterator
from pathlib import Path

_SHT_SYMTAB = 2


_ELF32_SHDR = struct.Struct("<IIIIIIIIII")


_ELF32_SYM = struct.Struct("<IIIBBH")


_ELF32_HEADER_SHOFF = struct.Struct("<I")


_ELF32_SHENT = struct.Struct("<HH")


_E_SHOFF_OFFSET = 32


_E_SHENTSIZE_OFFSET = 46


def elf_symbol(elf: Path, name: str) -> int:
    """Read a symbol address from the symbol table of a 32-bit ELF.

    Parameters
    ----------
    elf : Path
        The ELF file.
    name : str
        The symbol, for example `tohost`.

    Returns
    -------
    int
        The address of the symbol.

    Raises
    ------
    KeyError
        The ELF has no symbol of that name.
    """
    data = elf.read_bytes()
    for table in _symbol_tables(data):
        for sym_name, value in _symbols(data, table):
            if sym_name == name:
                return value
    raise KeyError(f"{elf} has no symbol {name!r}")


def _symbol_tables(data: bytes) -> Iterator[tuple[int, int, int, int]]:
    """Find the symbol tables of a 32-bit ELF.

    Parameters
    ----------
    data : bytes
        The contents of the ELF.

    Yields
    ------
    tuple of int
        For every `SHT_SYMTAB` section, the file offset and size of its
        entries, the entry size and the file offset of its string
        table.
    """
    (shoff,) = _ELF32_HEADER_SHOFF.unpack_from(data, _E_SHOFF_OFFSET)
    shentsize, shnum = _ELF32_SHENT.unpack_from(data, _E_SHENTSIZE_OFFSET)
    for index in range(shnum):
        header = _ELF32_SHDR.unpack_from(data, shoff + index * shentsize)
        kind, offset, size, link, entsize = (
            header[1],
            header[4],
            header[5],
            header[6],
            header[9],
        )
        if kind != _SHT_SYMTAB or not entsize:
            continue
        str_header = _ELF32_SHDR.unpack_from(data, shoff + link * shentsize)
        yield offset, size, entsize, str_header[4]


def _symbols(
    data: bytes, table: tuple[int, int, int, int]
) -> Iterator[tuple[str, int]]:
    """List the symbols of one symbol table.

    Parameters
    ----------
    data : bytes
        The contents of the ELF.
    table : tuple of int
        One item of `_symbol_tables`.

    Yields
    ------
    tuple of (str, int)
        The name and the address of each symbol.
    """
    offset, size, entsize, str_offset = table
    for sym in range(size // entsize):
        sym_name, value, *_ = _ELF32_SYM.unpack_from(
            data, offset + sym * entsize
        )
        end = data.index(b"\0", str_offset + sym_name)
        yield data[str_offset + sym_name : end].decode(), value
