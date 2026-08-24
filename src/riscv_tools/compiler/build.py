import subprocess
from pathlib import Path

from .headers import parse_header


def compile_test(
    toolchain_cfg: dict,
    isa_cfg: dict,
    default_timeout_s: float,
    c_file: Path,
    build_dir: Path,
    include_dir: Path,
    crt0: Path,
    linker: Path,
) -> tuple[Path, str, str, float]:
    """Compiles one bare-metal test source (.c or .S) against crt0/linker
    into a flat binary.

    Args:
        toolchain_cfg: The project's `toolchain:` config section —
            needs `gcc` and `objcopy` (binary names or full paths).
        isa_cfg: The project's `isa:` config section, passed through
            to headers.parse_header.
        default_timeout_s: Timeout to use if c_file has no `//
            RV32_TIMEOUT_S:` header, passed through to
            headers.parse_header.
        c_file: Path to the test source (.c or .S) to compile.
        build_dir: Directory to write the .elf/.bin into (created if
            missing).
        include_dir: Passed as `-I` — where `rv32_test.h` lives.
        crt0: Path to the project's crt0.S, compiled and linked in
            alongside c_file.
        linker: Path to the project's linker script, passed as
            `-Wl,-T,`.

    Returns:
        A (bin_path, march, kind, timeout_s) tuple: the path to the
        flat .bin produced (build_dir/<c_file stem>.bin), and the
        march/kind/timeout_s resolved from c_file's header comments
        (see headers.parse_header).
    """
    march, kind, timeout_s = parse_header(isa_cfg, default_timeout_s, c_file.read_text())

    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / f"{c_file.stem}.elf"
    bin_ = build_dir / f"{c_file.stem}.bin"

    subprocess.run(
        [
            toolchain_cfg["gcc"],
            f"-march={march}", "-mabi=ilp32", "-Os",
            "-ffreestanding", "-nostdlib", "-nostartfiles",
            f"-I{include_dir}",
            f"-Wl,-T,{linker}",
            str(crt0), str(c_file),
            "-o", str(elf),
        ],
        check=True,
    )
    subprocess.run([toolchain_cfg["objcopy"], "-O", "binary", str(elf), str(bin_)], check=True)
    return bin_, march, kind, timeout_s
