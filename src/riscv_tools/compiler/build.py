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
    """Compiles one bare-metal test source (.c or .S) against crt0/linker,
    returning (bin_path, march, kind, timeout_s) — see headers.py for
    where march/kind/timeout_s come from."""
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
