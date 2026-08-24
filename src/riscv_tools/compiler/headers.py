"""Per-test header conventions, read from comments at the top of a
.c/.S source file:

  // RV32_EXT: M          -> compiled with -march=rv32im (additions to
  // RV32_EXT: M,A        -> the implicit rv32i base; order doesn't
                              matter, normalized via isa.canonical_order)
  // RV32_TEST_KIND: unit          -> default. Checked via the PASS/FAIL
                                       mailbox only.
  // RV32_TEST_KIND: memory        -> also dumps RAM and compares it
                                       against a golden JSON.
  // RV32_TIMEOUT_S: 5              -> how long the orchestrator waits
                                       for this test's mailbox before
                                       falling back to a full reprogram.
                                       Defaults to orchestrator's
                                       default_timeout_s.
"""
import re

EXT_RE = re.compile(r"^\s*//\s*RV32_EXT:\s*(.+?)\s*$", re.MULTILINE)
KIND_RE = re.compile(r"^\s*//\s*RV32_TEST_KIND:\s*(unit|memory)\s*$", re.MULTILINE)
TIMEOUT_RE = re.compile(r"^\s*//\s*RV32_TIMEOUT_S:\s*([0-9.]+)\s*$", re.MULTILINE)


def canonical_march(isa_cfg: dict, ext_csv: str) -> str:
    """Builds a normalized `-march=` string from a test's `RV32_EXT`
    header value.

    Args:
        isa_cfg: The project's `isa:` config section — needs `base`
            (the always-implied base ISA letter, e.g. "i") and
            `canonical_order` (the extension-letter order to sort by).
        ext_csv: The raw, comma-separated extension list from a test's
            `// RV32_EXT:` header (e.g. "M,A"), or "" if the test has
            no such header.

    Returns:
        The full march string, e.g. "rv32ima". Extension order in
        ext_csv doesn't affect the result — "M,A" and "A,M" both
        produce the same string, per canonical_order.

    Raises:
        ValueError: ext_csv names a letter not present in
            isa_cfg["canonical_order"].
    """
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
    """Reads a test source's `RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`
    header comments and resolves them to concrete build/run values.

    Args:
        isa_cfg: The project's `isa:` config section — passed straight
            through to canonical_march.
        default_timeout_s: Timeout to use when the source has no
            `// RV32_TIMEOUT_S:` header (normally
            cfg["quartus"]["default_timeout_s"]).
        text: The full source file contents to search for header
            comments.

    Returns:
        A (march, kind, timeout_s) tuple: the normalized `-march=`
        string (see canonical_march), the test kind ("unit" or
        "memory", "unit" if the header is absent), and the timeout in
        seconds (default_timeout_s if the header is absent).
    """
    ext_match = EXT_RE.search(text)
    ext_csv = ext_match.group(1) if ext_match else ""
    kind_match = KIND_RE.search(text)
    kind = kind_match.group(1) if kind_match else "unit"
    timeout_match = TIMEOUT_RE.search(text)
    timeout_s = float(timeout_match.group(1)) if timeout_match else float(default_timeout_s)
    march = canonical_march(isa_cfg, ext_csv)
    return march, kind, timeout_s
