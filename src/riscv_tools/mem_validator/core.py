"""Compares a RAM dump (.mif, one 32-bit word per line) against a
golden JSON of expected byte values. Used for RV32_TEST_KIND:
memory tests, where the PASS/FAIL mailbox alone isn't enough to
prove the test did the right thing — e.g. it wrote the right values to
memory, not just that it reached RV32_PASS()."""
import json
import re
from pathlib import Path

CONTENT_RE = re.compile(r"CONTENT\s+BEGIN(.*)END\s*;", re.IGNORECASE | re.DOTALL)
LINE_RE = re.compile(r"^\s*([0-9A-Fa-f]+)\s*:\s*([0-9A-Fa-f]+)\s*;")
RANGE_RE = re.compile(r"^\s*\[([0-9A-Fa-f]+)\.\.([0-9A-Fa-f]+)\]\s*:\s*([0-9A-Fa-f]+)\s*;")


def parse_mif_words(mif_path: Path) -> dict:
    """Parses a .mif's CONTENT BEGIN...END; block into a word map.

    Handles both single-address lines (`ADDR : VALUE;`) and Quartus'
    address-range lines (`[START..END] : VALUE;`, used to fill unused
    depth), as produced by mem_edit.dump/ram_dump.dump_ram.

    Args:
        mif_path: Path to the .mif to parse.

    Returns:
        A {word_address: word_value} dict, one entry per word address
        covered by the file's CONTENT block (single lines and
        expanded ranges alike).

    Raises:
        ValueError: mif_path has no CONTENT ... END; block.
    """
    text = mif_path.read_text()
    m = CONTENT_RE.search(text)
    if not m:
        raise ValueError(f"{mif_path}: no CONTENT ... END; block found")
    words = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        rm = RANGE_RE.match(line)
        if rm:
            start, end, val = int(rm.group(1), 16), int(rm.group(2), 16), int(rm.group(3), 16)
            for addr in range(start, end + 1):
                words[addr] = val
            continue
        lm = LINE_RE.match(line)
        if lm:
            words[int(lm.group(1), 16)] = int(lm.group(2), 16)
    return words


def words_to_bytes(words: dict) -> dict:
    """Expands a word map into a byte map, little-endian.

    Args:
        words: A {word_address: word_value} dict, as returned by
            parse_mif_words (word_address is a WORD index, not a byte
            address).

    Returns:
        A {byte_address: byte_value} dict — each word_address maps to
        4 consecutive byte_address entries (word_address*4 ..
        word_address*4+3), least-significant byte first.
    """
    out = {}
    for waddr, wval in words.items():
        base = waddr * 4
        for i in range(4):
            out[base + i] = (wval >> (8 * i)) & 0xFF
    return out


def compare(dump_mif: Path, golden_json: Path) -> bool:
    """Compares a RAM dump against a golden JSON and prints a
    human-readable diff (OK/FAIL, with a per-address breakdown of the
    first 50 mismatches on failure).

    Args:
        dump_mif: Path to a RAM dump .mif (e.g. from
            ram_dump.dump_ram).
        golden_json: Path to the golden JSON — a {hex byte address
            string: expected int byte value} map. Only the addresses
            listed here are checked; extra bytes in dump_mif that
            aren't in golden_json are ignored.

    Returns:
        True if every address in golden_json matches dump_mif's
        content exactly, False otherwise.
    """
    actual = words_to_bytes(parse_mif_words(dump_mif))
    golden = {int(k, 16): int(v) for k, v in json.loads(golden_json.read_text()).items()}

    diffs = []
    for addr, expected in sorted(golden.items()):
        got = actual.get(addr)
        if got is None:
            diffs.append((addr, expected, None))
        elif got != expected:
            diffs.append((addr, expected, got))

    if not diffs:
        print(f"OK: {dump_mif.name} matches {golden_json.name}")
        return True

    print(f"FAIL: {dump_mif.name} differs from {golden_json.name}:")
    for addr, expected, got in diffs[:50]:
        got_str = "missing" if got is None else f"0x{got:02X}"
        print(f"  0x{addr:08X}: expected 0x{expected:02X}, got {got_str}")
    if len(diffs) > 50:
        print(f"  ... and {len(diffs) - 50} more")
    return False
