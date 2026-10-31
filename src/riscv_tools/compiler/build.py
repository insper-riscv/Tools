"""Compiles one bare-metal test source (.c or .S) into a flat binary."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from riscv_tools.compiler.headers import parse_header

_LIBC_FLAGS = {
    # No libc: a project needing malloc() and friends supplies its own
    # (paths.syscalls). Safe with any toolchain, including a downloaded
    # one whose bundled libc.a targets another ABI (the riscv-collab
    # release ships a single rv32imafdc/hard-float one, unusable with
    # -mabi=ilp32).
    "none": ["-nostdlib"],
    # picolibc, for a toolchain configured with it (insper-riscv/Infra's
    # GCC_SETUP.md builds one for rv32im/ilp32). picolibc.specs turns on
    # --gc-sections, which drops every section a link script doesn't
    # KEEP or reach from its entry, so it is switched off again.
    "picolibc": ["--specs=picolibc.specs", "-Wl,--no-gc-sections"],
}


def libc_flags(toolchain_cfg: dict[str, Any]) -> list[str]:
    """Return the gcc flags that select the C library (toolchain.libc).

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
            f"toolchain.libc must be one of {sorted(_LIBC_FLAGS)}, "
            f"got {libc!r}"
        )
    return list(_LIBC_FLAGS[libc])


def _linker_script_flags(linker: Path | None) -> list[str]:
    """Return the gcc flags that select a project's own linker script.

    Parameters
    ----------
    linker : Path or None
        The project's linker script, or None to leave it to the
        toolchain.

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


@dataclass(frozen=True)
class LinkSetup:
    """What goes into the link of a test besides the test itself.

    Attributes
    ----------
    crt0 : Path or None
        Path to the project's crt0.S, compiled and linked in alongside
        the test (which also turns the toolchain's startup files off).
        None to use the toolchain's crt0.
    linker : Path or None
        Path to the project's linker script, passed as `-T`. None to
        use the toolchain's (picolibc.ld, which the GCC driver adds
        when it sees no `-T`).
    extra_sources : list of Path
        Additional source files compiled in alongside crt0 and the test,
        before the test on the command line (for example a shared
        bootloader linked into one self-contained ELF). Empty by
        default.
    link_flags : list of str
        Extra gcc arguments placed before the sources (for that
        combined ELF: where the boot ROM's sections go, the entry
        symbol). Empty by default.
    """

    crt0: Path | None = None
    linker: Path | None = None
    extra_sources: list[Path] = field(default_factory=list[Path])
    link_flags: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class BuildSetup:
    """The build settings shared by every test of a project.

    Attributes
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; needs `gcc` and
        `objcopy` (binary names or full paths). `specs`, when set,
        must be a path that resolves from the current directory (the
        CLI makes it absolute).
    isa_cfg : dict of {str: Any}
        The project's `isa:` config section, passed through to
        headers.parse_header.
    default_timeout_s : float
        Timeout to use if a test has no `// RV32_TIMEOUT_S:` header,
        passed through to headers.parse_header.
    include_dir : Path
        Passed as `-I`, where `rv32_test.h` lives.
    link : LinkSetup
        Startup file, linker script and extra link inputs. The
        defaults use the toolchain's own.
    """

    toolchain_cfg: dict[str, Any]
    isa_cfg: dict[str, Any]
    default_timeout_s: float
    include_dir: Path
    link: LinkSetup = field(default_factory=LinkSetup)


def optimize_flags(march: str) -> list[str]:
    """Return the gcc flags that pick the ISA, the ABI and -Os.

    Parameters
    ----------
    march : str
        The `-march` value (see headers.canonical_march).

    Returns
    -------
    list of str
        The flags shared by every compile of a test source.
    """
    return [f"-march={march}", "-mabi=ilp32", "-Os"]


def run_gcc(toolchain_cfg: dict[str, Any], args: list[str]) -> None:
    """Run the project's gcc with args, raising if it fails.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; needs `gcc`.
    args : list of str
        Everything after the gcc binary on the command line.

    Raises
    ------
    subprocess.CalledProcessError
        gcc exited non-zero.
    """
    subprocess.run([str(toolchain_cfg["gcc"]), *args], check=True)


def elf_to_bin(toolchain_cfg: dict[str, Any], elf: Path, bin_: Path) -> None:
    """Write an ELF's loadable content as a flat binary.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; needs `objcopy`.
    elf : Path
        Linked ELF to convert.
    bin_ : Path
        Path to write the flat binary to (overwritten if it exists).

    Raises
    ------
    subprocess.CalledProcessError
        `objcopy` failed.
    """
    subprocess.run(
        [str(toolchain_cfg["objcopy"]), "-O", "binary", str(elf), str(bin_)],
        check=True,
    )


def compile_test(
    setup: BuildSetup, c_file: Path, name: str, build_dir: Path
) -> tuple[Path, str, str, float]:
    """Compile one bare-metal test source (.c or .S) into a flat binary.

    The runtime comes from one of two places. With `toolchain.specs`,
    the test is a hosted program linked by `--specs=<file>` against the
    toolchain's own crt0 and linker script, which the specs file selects
    and gives the memory map to, so crt0 and linker are None. Without
    it, the project's own crt0 and linker script are linked in, as
    before.

    Parameters
    ----------
    setup : BuildSetup
        The build settings shared by every test of the project.
    c_file : Path
        Path to the test source (.c or .S) to compile.
    name : str
        This test's name, used for the output .elf/.bin basename,
        not necessarily c_file.stem, since every test source is
        conventionally named `src.c`/`src.S` inside its own
        <c_dir|asm_dir>/<name>/ folder (see cli.py's test discovery).
    build_dir : Path
        Directory to write the .elf/.bin into (created if missing).

    Returns
    -------
    tuple of (Path, str, str, float)
        A (bin_path, march, kind, timeout_s) tuple: the path to the
        flat .bin produced (build_dir/<name>.bin), and the
        march/kind/timeout_s resolved from c_file's header comments
        (see headers.parse_header).
    """
    toolchain_cfg = setup.toolchain_cfg
    crt0 = setup.link.crt0
    march, kind, timeout_s = parse_header(
        setup.isa_cfg, setup.default_timeout_s, c_file.read_text()
    )

    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / f"{name}.elf"
    bin_ = build_dir / f"{name}.bin"

    # A C memory test is checked through its `results` array, which it
    # may only declare (a test that just checks .bss is zeroed never
    # reads it). The toolchain's linker script collects unreferenced
    # sections (--gc-sections), so the symbol is named as needed to keep
    # it.
    keep_results = (
        ["-Wl,--undefined=results"]
        if kind == "memory" and c_file.suffix == ".c"
        else []
    )

    specs = toolchain_cfg.get("specs")
    # A specs file describes a hosted platform: main() returns to the
    # crt0, which calls exit(), so the compiler must not be told the
    # program is freestanding (that also drops main's implicit return
    # 0).
    runtime_flags = (
        [f"--specs={specs}"]
        if specs
        else ["-ffreestanding", *libc_flags(toolchain_cfg)]
    )

    run_gcc(
        toolchain_cfg,
        [
            *optimize_flags(march),
            *runtime_flags,
            # Own startup file: the toolchain's are turned off.
            *(["-nostartfiles"] if crt0 is not None else []),
            f"-I{setup.include_dir}",
            *_linker_script_flags(setup.link.linker),
            *keep_results,
            *setup.link.link_flags,
            *([str(crt0)] if crt0 is not None else []),
            *[str(p) for p in setup.link.extra_sources],
            str(c_file),
            "-o",
            str(elf),
        ],
    )
    elf_to_bin(toolchain_cfg, elf, bin_)
    return bin_, march, kind, timeout_s


def elf_to_verilog_hex(
    toolchain_cfg: dict[str, Any], elf: Path, hex_path: Path
) -> None:
    """Write an ELF's loadable content as a Verilog-style hex file.

    Uses `objcopy -O verilog` with one 32-bit word per entry. The file
    has a `@<word address>` line wherever the image starts or jumps, so
    a program linked above address 0 keeps its real word address and
    needs no leading zero padding; four words share a line.

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
