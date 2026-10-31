"""Find the test sources of a project."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CTest:
    """The identity of one C test.

    Parameters
    ----------
    name : str
        This test's name.
    march : str
        This test's own `-march=` string (from compiler.compile_test).
    src : Path
        This test's own source file (.c).
    """

    name: str
    march: str
    src: Path


def discover_tests(root: Path, cfg: dict[str, Any]) -> list[Path]:
    """Find every test source under paths.c_dir/paths.asm_dir.

    Each test is a <c_dir|asm_dir>/<name>/ folder with exactly one
    `src.c` or `src.S` and, for "memory"-kind tests, a `golden.json`
    with the expected {byte address: byte value} map.

    A folder with a `.off` file is skipped, and the file's content is
    printed as the reason. Use it for a test that can never build or run
    on this target, not to silence a test that should work.

    Parameters
    ----------
    root : Path
        The consuming project's root directory.
    cfg : dict of {str: Any}
        The merged project config: uses paths.c_dir/paths.asm_dir.

    Returns
    -------
    list of Path
        Every `src.c`/`src.S` found (excluding `.off` folders), sorted
        by test name (the parent folder's name); folder names must be
        unique across c_dir/asm_dir combined.
    """
    c_dir = root / cfg["paths"]["c_dir"]
    asm_dir = root / cfg["paths"]["asm_dir"]
    sources = list(c_dir.glob("*/src.c")) + list(asm_dir.glob("*/src.S"))

    kept: list[Path] = []
    for src in sources:
        off_marker = src.parent / ".off"
        if off_marker.is_file():
            reason = off_marker.read_text().strip()
            suffix = f": {reason}" if reason else ""
            print(f"Skipping {src.parent.name} (.off present){suffix}")
            continue
        kept.append(src)

    return sorted(kept, key=lambda p: p.parent.name)
