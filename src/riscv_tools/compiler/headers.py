"""Per-test header conventions, read from comments in a .c/.S source.

    // RV32_EXT: M,A           extensions added to the rv32i base
    // RV32_TEST_KIND: unit    (default) PASS/FAIL by tohost only
    // RV32_TEST_KIND: memory  also compares RAM with a golden JSON
    // RV32_TIMEOUT_S: 5       seconds to wait for tohost

The extensions may come in any order; they are normalized with
isa.canonical_order. Without a timeout header the project's default
timeout applies.
"""

import re
from typing import Any

EXT_RE = re.compile(r"^\s*//\s*RV32_EXT:\s*(.+?)\s*$", re.MULTILINE)
KIND_RE = re.compile(
    r"^\s*//\s*RV32_TEST_KIND:\s*(unit|memory)\s*$", re.MULTILINE
)
TIMEOUT_RE = re.compile(
    r"^\s*//\s*RV32_TIMEOUT_S:\s*([0-9.]+)\s*$", re.MULTILINE
)


def canonical_march(isa_cfg: dict[str, Any], ext_csv: str) -> str:
    """Build a normalized `-march=` string from a `RV32_EXT` header.

    Parameters
    ----------
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section: needs `base` (the
        always-implied base ISA letter, e.g. "i") and
        `canonical_order` (the extension-letter order to sort by).
    ext_csv : str
        The raw, comma-separated extension list from a test's `//
        RV32_EXT:` header (e.g. "M,A"), or "" if the test has no such
        header.

    Returns
    -------
    str
        The full march string, e.g. "rv32ima" or "rv32im_zicsr".
        Extension order in ext_csv doesn't affect the result; "M,A" and
        "A,M" both produce the same string, per canonical_order.

    Raises
    ------
    ValueError
        ext_csv names a letter not present in
        isa_cfg["canonical_order"].
    """
    base = "rv32" + isa_cfg["base"]
    if not ext_csv:
        return base
    order = isa_cfg["canonical_order"]
    names = {e.strip().upper() for e in ext_csv.split(",") if e.strip()}
    # Multi-letter extensions (Zicsr, Zifencei, ...) start with Z and
    # come after the single-letter ones, each preceded by "_" and sorted
    # alphabetically.
    multi = {n for n in names if len(n) > 1 and n[0] == "Z"}
    letters = names - multi
    unknown = letters - set(order)
    if unknown:
        raise ValueError(
            f"Unknown extension(s) {sorted(unknown)}; add them to "
            f"isa.canonical_order in config.yaml"
        )
    sorted_ext = "".join(
        letter for letter in order if letter in letters
    ).lower()
    sorted_multi = "".join(f"_{name.lower()}" for name in sorted(multi))
    return base + sorted_ext + sorted_multi


def parse_header(
    isa_cfg: dict[str, Any], default_timeout_s: float, text: str
) -> tuple[str, str, float]:
    """Resolve a test source's header comments to build/run values.

    Reads `RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S` header comments.

    Parameters
    ----------
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section: passed straight through
        to canonical_march.
    default_timeout_s : float
        Timeout to use when the source has no `// RV32_TIMEOUT_S:`
        header (normally cfg["quartus"]["default_timeout_s"]).
    text : str
        The full source file contents to search for header comments.

    Returns
    -------
    tuple of (str, str, float)
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
    timeout_s = (
        float(timeout_match.group(1))
        if timeout_match
        else float(default_timeout_s)
    )
    march = canonical_march(isa_cfg, ext_csv)
    return march, kind, timeout_s
