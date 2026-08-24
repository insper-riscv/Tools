"""Flat .bin -> hardware-loadable format conversions. No JTAG/hardware
interaction here — that's rom_writer/ram_zero's job."""
import struct
from pathlib import Path


def read_words(bin_path: Path) -> list[int]:
    data = Path(bin_path).read_bytes()
    if len(data) % 4:
        data += b"\x00" * (4 - len(data) % 4)
    return [w for (w,) in struct.iter_unpack("<I", data)]


def bin_to_mif(bin_path: Path, mif_path: Path, depth: int) -> int:
    """Converts a flat RV32 .bin into an Intel/Altera .mif, for a
    memory IP that Quartus reads at synthesis time or an
    in-system-memory-editor full-depth write (mem_edit.write_full)."""
    words = read_words(bin_path)
    if len(words) > depth:
        raise ValueError(f"{bin_path}: program is {len(words)} words, memory only holds {depth}")

    lines = ["WIDTH=32;", f"DEPTH={depth};", "", "ADDRESS_RADIX=HEX;", "DATA_RADIX=HEX;", "", "CONTENT BEGIN"]
    for i, w in enumerate(words):
        lines.append(f"    {i:04X} : {w:08X};")
    if len(words) < depth:
        lines.append(f"    [{len(words):04X}..{depth - 1:04X}] : 00000000;")
    lines.append("END;")

    Path(mif_path).write_text("\n".join(lines) + "\n")
    return len(words)


def bin_to_hex(bin_path: Path, hex_path: Path) -> int:
    """Converts a flat RV32 .bin into plain-text hex (one 32-bit word
    per line) — the format a cocotb/GHDL sim testbench loads."""
    words = read_words(bin_path)
    Path(hex_path).write_text("\n".join(f"{w:08X}" for w in words) + "\n")
    return len(words)
