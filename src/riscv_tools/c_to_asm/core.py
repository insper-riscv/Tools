"""Compile a single RISC-V C source to human-readable assembly (gcc -S).

For inspecting/debugging codegen — a distinct concern from `compiler`
(which links a full test binary for the mif/hex/JTAG pipeline, not
just one translation unit). A .S source is already assembly and is
copied through unchanged.
"""

import subprocess
from pathlib import Path
from typing import Any

from riscv_tools.compiler.headers import EXT_RE, canonical_march


def c_to_asm(
    toolchain_cfg: dict[str, Any],
    isa_cfg: dict[str, Any],
    c_file: Path,
    out_dir: Path,
    include_dir: Path,
) -> Path:
    """Compile a single C source to RISC-V assembly.

    Passes a .S source through unchanged.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section — needs `gcc`
        (binary name or full path). Unused if c_file is already
        assembly.
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section, used to resolve c_file's
        `// RV32_EXT:` header into a `-march=` string. Unused if
        c_file is already assembly.
    c_file : Path
        Path to the source (.c or .S) to process.
    out_dir : Path
        Directory to write the .s file into (created if missing).
    include_dir : Path
        Passed as `-I` — where `rv32_test.h` lives. Unused if c_file
        is already assembly.

    Returns
    -------
    Path
        Path to the resulting assembly file (out_dir/<c_file stem>.s).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    asm = out_dir / f"{c_file.stem}.s"

    if c_file.suffix == ".S":
        asm.write_text(c_file.read_text())
        return asm

    ext_match = EXT_RE.search(c_file.read_text())
    ext_csv = ext_match.group(1) if ext_match else ""
    march = canonical_march(isa_cfg, ext_csv)

    subprocess.run(
        [
            str(toolchain_cfg["gcc"]),
            f"-march={march}",
            "-mabi=ilp32",
            "-Os",
            "-ffreestanding",
            "-nostdlib",
            f"-I{include_dir}",
            "-S",
            str(c_file),
            "-o",
            str(asm),
        ],
        check=True,
    )
    return asm
