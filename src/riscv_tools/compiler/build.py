"""Compiles one bare-metal test source (.c or .S) into a flat binary."""

import subprocess
from pathlib import Path
from typing import Any

from .headers import parse_header


# Each arg below is an independent gcc input, not bundleable without a
# config object this module doesn't otherwise need.
def compile_test(  # noqa: PLR0913, PLR0917
    toolchain_cfg: dict[str, Any],
    isa_cfg: dict[str, Any],
    default_timeout_s: float,
    c_file: Path,
    name: str,
    build_dir: Path,
    include_dir: Path,
    crt0: Path,
    linker: Path,
) -> tuple[Path, str, str, float]:
    """Compile one bare-metal test source (.c or .S) against crt0/linker.

    Produces a flat binary.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section — needs `gcc` and
        `objcopy` (binary names or full paths).
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section, passed through to
        headers.parse_header.
    default_timeout_s : float
        Timeout to use if c_file has no `// RV32_TIMEOUT_S:` header,
        passed through to headers.parse_header.
    c_file : Path
        Path to the test source (.c or .S) to compile.
    name : str
        This test's name, used for the output .elf/.bin basename —
        not necessarily c_file.stem, since every test source is
        conventionally named `src.c`/`src.S` inside its own
        <c_dir|asm_dir>/<name>/ folder (see cli.py's test discovery).
    build_dir : Path
        Directory to write the .elf/.bin into (created if missing).
    include_dir : Path
        Passed as `-I` — where `rv32_test.h` lives.
    crt0 : Path
        Path to the project's crt0.S, compiled and linked in alongside
        c_file.
    linker : Path
        Path to the project's linker script, passed as `-Wl,-T,`.

    Returns
    -------
    tuple of (Path, str, str, float)
        A (bin_path, march, kind, timeout_s) tuple: the path to the
        flat .bin produced (build_dir/<name>.bin), and the
        march/kind/timeout_s resolved from c_file's header comments
        (see headers.parse_header).
    """
    march, kind, timeout_s = parse_header(
        isa_cfg, default_timeout_s, c_file.read_text()
    )

    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / f"{name}.elf"
    bin_ = build_dir / f"{name}.bin"

    subprocess.run(
        [
            str(toolchain_cfg["gcc"]),
            f"-march={march}",
            "-mabi=ilp32",
            "-Os",
            "-ffreestanding",
            "-nostdlib",
            "-nostartfiles",
            f"-I{include_dir}",
            f"-Wl,-T,{linker}",
            str(crt0),
            str(c_file),
            "-o",
            str(elf),
        ],
        check=True,
    )
    subprocess.run(
        [str(toolchain_cfg["objcopy"]), "-O", "binary", str(elf), str(bin_)], check=True
    )
    return bin_, march, kind, timeout_s
