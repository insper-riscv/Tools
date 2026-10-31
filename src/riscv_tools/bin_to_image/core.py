"""Convert a flat .bin into hardware/sim-loadable formats (.mif, .hex).

A distinct concern from `compiler` (source -> .elf/.bin): this module
only ever touches an already-compiled flat binary, never a compiler.
No JTAG/hardware interaction either; that's rom_writer/ram_zero's
job.
"""

import struct
from pathlib import Path

_WORD = struct.Struct("<I")


def mif_text(depth: int, content: list[str]) -> str:
    """Build the text of a .mif with 32-bit words and hex radix.

    Parameters
    ----------
    depth : int
        Word depth of the memory the .mif describes.
    content : list of str
        The lines between `CONTENT BEGIN` and `END;`.

    Returns
    -------
    str
        The complete .mif, ending with a newline.
    """
    lines = [
        "WIDTH=32;",
        f"DEPTH={depth};",
        "",
        "ADDRESS_RADIX=HEX;",
        "DATA_RADIX=HEX;",
        "",
        "CONTENT BEGIN",
        *content,
        "END;",
    ]
    return "\n".join(lines) + "\n"


def read_words(bin_path: Path, pad_words: int = 0) -> list[int]:
    """Read a flat binary as little-endian 32-bit words.

    `objcopy -O binary` starts the file at the ELF's lowest address,
    so a FLASH image linked at 0x800 would land at word 0; pad_words
    restores its real word index.

    Parameters
    ----------
    bin_path : Path
        Path to the flat .bin file (e.g. from `objcopy -O binary`).
        Zero-padded up to the next 4-byte boundary if its length isn't
        a multiple of 4.
    pad_words : int, optional
        Zero words to prepend before the file's content, for a memory
        addressed raw from a nonzero base (for example a FLASH linked at
        0x800). Default 0.

    Returns
    -------
    list of int
        `pad_words` zeros, followed by the file's content as 32-bit
        unsigned ints, in file order.
    """
    data = Path(bin_path).read_bytes()
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    return [0] * pad_words + [w for (w,) in _WORD.iter_unpack(data)]


def bin_to_mif(
    bin_path: Path, mif_path: Path, depth: int, pad_words: int = 0
) -> int:
    """Convert a flat RV32 .bin into an Intel/Altera .mif.

    For a memory IP that Quartus reads at synthesis time or an
    in-system-memory-editor full-depth write (mem_edit.write_full).

    Parameters
    ----------
    bin_path : Path
        Path to the source flat .bin file.
    mif_path : Path
        Path to write the .mif to (overwritten if it already exists).
    depth : int
        Total word depth of the target memory. Addresses beyond the
        program's own words are filled with zero via a MIF
        address-range entry.
    pad_words : int, optional
        Zero words to prepend before the file's content, for a memory
        addressed raw from a nonzero base (for example a FLASH linked at
        0x800). Default 0.

    Returns
    -------
    int
        The number of words actually read from bin_path (<= depth).

    Raises
    ------
    ValueError
        bin_path has more words than depth.
    """
    words = read_words(bin_path, pad_words=pad_words)
    if len(words) > depth:
        raise ValueError(
            f"{bin_path}: program is {len(words)} words, "
            f"memory only holds {depth}"
        )

    content = [f"    {i:04X} : {w:08X};" for i, w in enumerate(words)]
    if len(words) < depth:
        content.append(f"    [{len(words):04X}..{depth - 1:04X}] : 00000000;")

    Path(mif_path).write_text(mif_text(depth, content), encoding="utf-8")
    return len(words)


def bin_to_hex(bin_path: Path, hex_path: Path, pad_words: int = 0) -> int:
    """Convert a flat RV32 .bin into plain hex, one word per line.

    The format a cocotb/GHDL sim testbench loads.

    Parameters
    ----------
    bin_path : Path
        Path to the source flat .bin file.
    hex_path : Path
        Path to write the .hex to (overwritten if it already exists).
    pad_words : int, optional
        Zero words to prepend before the file's content, for a memory
        addressed raw from a nonzero base (for example a FLASH linked at
        0x800). Default 0.

    Returns
    -------
    int
        The number of words written.
    """
    words = read_words(bin_path, pad_words=pad_words)
    Path(hex_path).write_text(
        "\n".join(f"{w:08X}" for w in words) + "\n", encoding="utf-8"
    )
    return len(words)
