"""Compile a single RISC-V C source to human-readable assembly (gcc -S).

For inspecting/debugging codegen, a distinct concern from `compiler`
(which links a full test binary for the mif/hex/JTAG pipeline, not
just one translation unit). A .S source is already assembly and is
copied through unchanged.
"""

from pathlib import Path
from typing import Any

from riscv_tools.compiler.build import optimize_flags, run_gcc
from riscv_tools.compiler.headers import EXT_RE, canonical_march


def c_to_asm(
    toolchain_cfg: dict[str, Any],
    isa_cfg: dict[str, Any],
    c_file: Path,
    asm_path: Path,
    include_dir: Path,
) -> Path:
    """Compile a single C source to RISC-V assembly.

    Passes a .S source through unchanged.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section: needs `gcc`
        (binary name or full path). Unused if c_file is already
        assembly.
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section, used to resolve c_file's
        `// RV32_EXT:` header into a `-march=` string. Unused if
        c_file is already assembly.
    c_file : Path
        Path to the source (.c or .S) to process.
    asm_path : Path
        Where to write the assembly file; its directory is created if
        missing.
    include_dir : Path
        Passed as `-I`, where `rv32_test.h` lives. Unused if c_file
        is already assembly.

    Returns
    -------
    Path
        asm_path, the assembly file written.
    """
    asm_path.parent.mkdir(parents=True, exist_ok=True)

    if c_file.suffix == ".S":
        asm_path.write_text(c_file.read_text())
        return asm_path

    ext_match = EXT_RE.search(c_file.read_text())
    ext_csv = ext_match.group(1) if ext_match else ""
    march = canonical_march(isa_cfg, ext_csv)

    run_gcc(
        toolchain_cfg,
        [
            *optimize_flags(march),
            "-ffreestanding",
            "-nostdlib",
            f"-I{include_dir}",
            "-S",
            str(c_file),
            "-o",
            str(asm_path),
        ],
    )
    return asm_path
