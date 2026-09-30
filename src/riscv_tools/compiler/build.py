"""Compiles one bare-metal test source (.c or .S) into a flat binary."""

import subprocess
from pathlib import Path
from typing import Any

from .headers import parse_header

_LIBC_FLAGS = {
    # No libc: a project needing malloc() and friends supplies its own
    # (paths.syscalls). Safe with any toolchain, including a downloaded one
    # whose bundled libc.a targets another ABI (the riscv-collab release
    # ships a single rv32imafdc/hard-float one, unusable with -mabi=ilp32).
    "none": ["-nostdlib"],
    # picolibc, for a toolchain configured with it (insper-riscv/Infra's
    # GCC_SETUP.md builds one for rv32im/ilp32). picolibc.specs turns on
    # --gc-sections, which drops every section a link script doesn't KEEP
    # or reach from its entry, so it is switched off again.
    "picolibc": ["--specs=picolibc.specs", "-Wl,--no-gc-sections"],
}


def libc_flags(toolchain_cfg: dict[str, Any]) -> list[str]:
    """Return the gcc flags that select the C library for `toolchain.libc`.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; `libc` is "none" (the
        default) or "picolibc".

    Returns
    -------
    list of str
        The flags to place on the gcc command line.

    Raises
    ------
    ValueError
        `libc` is neither "none" nor "picolibc".
    """
    libc = str(toolchain_cfg.get("libc", "none"))
    if libc not in _LIBC_FLAGS:
        raise ValueError(
            f"toolchain.libc must be one of {sorted(_LIBC_FLAGS)}, got {libc!r}"
        )
    return list(_LIBC_FLAGS[libc])


def _linker_script_flags(linker: Path | None) -> list[str]:
    """Return the gcc flags that select a project's own linker script.

    Parameters
    ----------
    linker : Path or None
        The project's linker script, or None to leave it to the toolchain.

    Returns
    -------
    list of str
        `-T <script>` plus `-L` for its directory (ld's own `INCLUDE`
        only searches the process cwd plus -L dirs, NOT the including
        script's own directory), or an empty list.
    """
    if linker is None:
        return []
    return [f"-Wl,-L,{linker.parent}", "-T", str(linker)]


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
    crt0: Path | None,
    linker: Path | None,
    extra_sources: list[Path] | None = None,
    link_flags: list[str] | None = None,
) -> tuple[Path, str, str, float]:
    """Compile one bare-metal test source (.c or .S) into a flat binary.

    The runtime comes from one of two places. With `toolchain.specs`, the
    test is a hosted program linked by `--specs=<file>` against the
    toolchain's own crt0 and linker script, which the specs file
    selects and gives the memory map to, so crt0 and linker are None.
    Without it, the project's own crt0 and linker script are linked in, as
    before.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section — needs `gcc` and
        `objcopy` (binary names or full paths); `specs`, when set, must
        be a path that resolves from the current directory (the CLI makes
        it absolute).
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
    crt0 : Path or None
        Path to the project's crt0.S, compiled and linked in alongside
        c_file (which also turns the toolchain's startup files off).
        None to use the toolchain's crt0.
    linker : Path or None
        Path to the project's linker script, passed as `-T`. None to
        use the toolchain's (picolibc.ld, which the GCC driver adds when
        it sees no `-T`).
    extra_sources : list of Path, optional
        Additional source files to compile in alongside crt0/c_file,
        before c_file on the command line (e.g. a fixed shared
        bootloader — see riscv_tools.boot_rom — linked together with
        crt0/c_file for a project that needs a single, self-contained
        ELF an offline reference model can run from cold; a project's
        normal, separately-linked BOOT_ROM never needs this). Empty
        by default — most callers don't need it.
    link_flags : list of str, optional
        Extra gcc arguments placed before the sources (for that combined
        ELF: where the boot ROM's sections go, the entry symbol). Empty
        by default.

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

    specs = toolchain_cfg.get("specs")
    # A specs file describes a hosted platform: main() returns to the
    # crt0, which calls exit(), so the compiler must not be told the
    # program is freestanding (that also drops main's implicit return 0).
    runtime_flags = (
        [f"--specs={specs}"]
        if specs
        else ["-ffreestanding", *libc_flags(toolchain_cfg)]
    )

    subprocess.run(
        [
            str(toolchain_cfg["gcc"]),
            f"-march={march}",
            "-mabi=ilp32",
            "-Os",
            *runtime_flags,
            # Own startup file: the toolchain's are turned off.
            *(["-nostartfiles"] if crt0 is not None else []),
            f"-I{include_dir}",
            *_linker_script_flags(linker),
            *(link_flags or []),
            *([str(crt0)] if crt0 is not None else []),
            *[str(p) for p in (extra_sources or [])],
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


def elf_to_verilog_hex(
    toolchain_cfg: dict[str, Any], elf: Path, hex_path: Path
) -> None:
    """Write an ELF's loadable content as a Verilog-style hex file.

    Uses `objcopy -O verilog` with one 32-bit word per entry. The file has
    a `@<word address>` line wherever the image starts or jumps, so a
    program linked above address 0 keeps its real word address and needs
    no leading zero padding; four words share a line.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; needs `objcopy`.
    elf : Path
        Linked ELF to convert.
    hex_path : Path
        Path to write the hex file to (overwritten if it exists).

    Returns
    -------
    None

    Raises
    ------
    subprocess.CalledProcessError
        `objcopy` failed.
    """
    subprocess.run(
        [
            str(toolchain_cfg["objcopy"]),
            "-O",
            "verilog",
            "--verilog-data-width=4",
            str(elf),
            str(hex_path),
        ],
        check=True,
    )
