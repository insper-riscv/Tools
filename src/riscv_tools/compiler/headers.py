"""Per-test header conventions, read from comments at the top of a
.c/.S source file:

  // RV32_EXT: M          -> compiled with -march=rv32im (additions to
  // RV32_EXT: M,A        -> the implicit rv32i base; order doesn't
                              matter, normalized via isa.canonical_order)
  // RV32_TEST_KIND: unit          -> default. Checked via the PASS/FAIL
                                       mailbox only.
  // RV32_TEST_KIND: integration   -> also dumps RAM and compares it
                                       against a golden JSON.
  // RV32_TIMEOUT_S: 5              -> how long the orchestrator waits
                                       for this test's mailbox before
                                       falling back to a full reprogram.
                                       Defaults to orchestrator's
                                       default_timeout_s.
"""
import re

EXT_RE = re.compile(r"^\s*//\s*RV32_EXT:\s*(.+?)\s*$", re.MULTILINE)
KIND_RE = re.compile(r"^\s*//\s*RV32_TEST_KIND:\s*(unit|integration)\s*$", re.MULTILINE)
TIMEOUT_RE = re.compile(r"^\s*//\s*RV32_TIMEOUT_S:\s*([0-9.]+)\s*$", re.MULTILINE)


def canonical_march(isa_cfg: dict, ext_csv: str) -> str:
    base = "rv32" + isa_cfg["base"]
    if not ext_csv:
        return base
    order = isa_cfg["canonical_order"]
    letters = {e.strip().upper() for e in ext_csv.split(",") if e.strip()}
    unknown = letters - set(order)
    if unknown:
        raise ValueError(
            f"Unknown extension(s) {sorted(unknown)}; add them to "
            f"isa.canonical_order in config.yaml"
        )
    sorted_ext = "".join(letter for letter in order if letter in letters).lower()
    return base + sorted_ext


def parse_header(isa_cfg: dict, default_timeout_s: float, text: str) -> tuple[str, str, float]:
    ext_match = EXT_RE.search(text)
    ext_csv = ext_match.group(1) if ext_match else ""
    kind_match = KIND_RE.search(text)
    kind = kind_match.group(1) if kind_match else "unit"
    timeout_match = TIMEOUT_RE.search(text)
    timeout_s = float(timeout_match.group(1)) if timeout_match else float(default_timeout_s)
    march = canonical_march(isa_cfg, ext_csv)
    return march, kind, timeout_s
