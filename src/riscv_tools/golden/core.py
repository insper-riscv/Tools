"""Compares a RAM dump (.mif, one 32-bit word per line) against a
golden JSON of expected byte values. Used for RV32_TEST_KIND:
integration tests, where the PASS/FAIL mailbox alone isn't enough to
prove the test did the right thing — e.g. it wrote the right values to
memory, not just that it reached RV32_PASS()."""
import json
import re
from pathlib import Path

CONTENT_RE = re.compile(r"CONTENT\s+BEGIN(.*)END\s*;", re.IGNORECASE | re.DOTALL)
LINE_RE = re.compile(r"^\s*([0-9A-Fa-f]+)\s*:\s*([0-9A-Fa-f]+)\s*;")
RANGE_RE = re.compile(r"^\s*\[([0-9A-Fa-f]+)\.\.([0-9A-Fa-f]+)\]\s*:\s*([0-9A-Fa-f]+)\s*;")


def parse_mif_words(mif_path: Path) -> dict:
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
    out = {}
    for waddr, wval in words.items():
        base = waddr * 4
        for i in range(4):
            out[base + i] = (wval >> (8 * i)) & 0xFF
    return out


def compare(dump_mif: Path, golden_json: Path) -> bool:
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
