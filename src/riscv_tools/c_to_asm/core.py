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


# Each arg is an independent gcc input, not bundleable without a
# config object this module doesn't otherwise need.
def c_to_asm(  # noqa: PLR0913, PLR0917
    toolchain_cfg: dict[str, Any],
    isa_cfg: dict[str, Any],
    c_file: Path,
    name: str,
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
    name : str
        This test's name, used for the output .s basename — not
        necessarily c_file.stem (see compiler.build.compile_test).
    out_dir : Path
        Directory to write the .s file into (created if missing).
    include_dir : Path
        Passed as `-I` — where `rv32_test.h` lives. Unused if c_file
        is already assembly.

    Returns
    -------
    Path
        Path to the resulting assembly file (out_dir/<name>.s).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    asm = out_dir / f"{name}.s"

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
