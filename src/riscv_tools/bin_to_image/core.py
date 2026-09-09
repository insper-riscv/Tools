"""Convert a flat .bin into hardware/sim-loadable formats (.mif, .hex).

A distinct concern from `compiler` (source -> .elf/.bin): this module
only ever touches an already-compiled flat binary, never a compiler.
No JTAG/hardware interaction either — that's rom_writer/ram_zero's
job.
"""

import struct
from pathlib import Path


def read_words(bin_path: Path, pad_words: int = 0) -> list[int]:
    """Read a flat binary as little-endian 32-bit words.

    Parameters
    ----------
    bin_path : Path
        Path to the flat .bin file (e.g. from `objcopy -O binary`).
        Zero-padded up to the next 4-byte boundary if its length isn't
        a multiple of 4.
    pad_words : int, optional
        Zero words to prepend before the file's own content. Needed
        whenever the target memory is addressed RAW (no base-address
        subtraction in hardware — see rv32im_pipeline_core.vhd's
        BOOT_ROM/FLASH split) and the ELF this .bin came from doesn't
        start at address 0: `objcopy -O binary` always emits a flat
        file starting at the ELF's own LOWEST vma as byte 0, silently
        dropping the leading gap — e.g. a FLASH image linked at
        FLASH_BASE=0x800 produces a .bin whose word 0 is really word
        index 0x200, not 0, but the memory model/IP indexes by the
        raw address either way. Confirmed by simulation: without this,
        FLASH_simulation read back all zeros past the boot_rom->flash
        jump (a test's own real content ends up living FLASH_BASE/4
        words too early in the array). Default 0 for a memory that
        already starts at address 0 (e.g. BOOT_ROM).

    Returns
    -------
    list of int
        `pad_words` zeros, followed by the file's content as 32-bit
        unsigned ints, in file order.
    """
    data = Path(bin_path).read_bytes()
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    return [0] * pad_words + [w for (w,) in struct.iter_unpack("<I", data)]


def bin_to_mif(bin_path: Path, mif_path: Path, depth: int, pad_words: int = 0) -> int:
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
        See read_words — zero words to prepend for a memory addressed
        raw from a nonzero base (e.g. FLASH). Default 0.

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
            f"{bin_path}: program is {len(words)} words, memory only holds {depth}"
        )

    lines = [
        "WIDTH=32;",
        f"DEPTH={depth};",
        "",
        "ADDRESS_RADIX=HEX;",
        "DATA_RADIX=HEX;",
        "",
        "CONTENT BEGIN",
    ]
    for i, w in enumerate(words):
        lines.append(f"    {i:04X} : {w:08X};")
    if len(words) < depth:
        lines.append(f"    [{len(words):04X}..{depth - 1:04X}] : 00000000;")
    lines.append("END;")

    Path(mif_path).write_text("\n".join(lines) + "\n")
    return len(words)


def bin_to_hex(bin_path: Path, hex_path: Path, pad_words: int = 0) -> int:
    """Convert a flat RV32 .bin into plain-text hex, one 32-bit word per line.

    The format a cocotb/GHDL sim testbench loads.

    Parameters
    ----------
    bin_path : Path
        Path to the source flat .bin file.
    hex_path : Path
        Path to write the .hex to (overwritten if it already exists).
    pad_words : int, optional
        See read_words — zero words to prepend for a memory addressed
        raw from a nonzero base (e.g. FLASH). Default 0.

    Returns
    -------
    int
        The number of words written.
    """
    words = read_words(bin_path, pad_words=pad_words)
    Path(hex_path).write_text("\n".join(f"{w:08X}" for w in words) + "\n")
    return len(words)
