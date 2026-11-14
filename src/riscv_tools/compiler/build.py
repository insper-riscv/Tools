"""Compiles one bare-metal test source (.c or .S) into a flat binary."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from riscv_tools.compiler.cxx import (
    CXX_STANDARD_FLAGS,
    cxx_enabled,
    cxx_flags,
    cxx_options,
    gxx_for,
    is_cxx_source,
    require_libstdcxx,
    without_cxx_only_flags,
)
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
        combined ELF: where the boot memory's sections go, the entry
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


def abi_for(march: str) -> str:
    """Pick the ABI that goes with a `-march` value.

    Parameters
    ----------
    march : str
        The `-march` value (see headers.canonical_march).

    Returns
    -------
    str
        `ilp32e` for the RV32E base (16 registers), `ilp32` otherwise.
    """
    return "ilp32e" if march.startswith("rv32e") else "ilp32"


#: Flags that hold every C source to ISO/IEC 9899:2024 (C23): the
#: standard mode (not gnu23) and every diagnostic as an error.
C_STANDARD_FLAGS = [
    "-std=c23",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
    "-Werror",
]


def optimize_flags(march: str, cxx: bool = False) -> list[str]:
    """Return the gcc flags that pick the ISA, the ABI, -Os and C23.

    Parameters
    ----------
    march : str
        The `-march` value (see headers.canonical_march).
    cxx : bool
        True for a C++ source, which is held to `CXX_STANDARD_FLAGS`
        instead.

    Returns
    -------
    list of str
        The flags shared by every compile of a test source, ending
        with `C_STANDARD_FLAGS` (or `CXX_STANDARD_FLAGS`).
    """
    return [
        f"-march={march}",
        f"-mabi={abi_for(march)}",
        "-Os",
        *(CXX_STANDARD_FLAGS if cxx else C_STANDARD_FLAGS),
    ]


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

    With `toolchain.specs`, the test is a hosted program linked by
    `--specs=<file>` against the toolchain's own crt0 and linker script,
    so crt0 and linker are None. Without it, the project's own crt0 and
    linker script are linked in.

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

    cxx = is_cxx_source(c_file)
    runtime_flags = _runtime_flags(toolchain_cfg, march, setup.link, cxx)
    # The g++ driver would take a .c file for C++, so the C and assembly
    # sources of a C++ test are compiled apart, as C.
    sources = (
        _compile_extras(
            setup, march, runtime_flags, build_dir / f"{name}.extras"
        )
        if cxx
        else [str(p) for p in setup.link.extra_sources]
    )

    run_gcc(
        {**toolchain_cfg, "gcc": gxx_for(toolchain_cfg)}
        if cxx
        else toolchain_cfg,
        [
            *optimize_flags(march, cxx),
            *(cxx_options(toolchain_cfg) if cxx else []),
            *runtime_flags,
            # Own startup file: the toolchain's are turned off.
            *(["-nostartfiles"] if crt0 is not None else []),
            f"-I{setup.include_dir}",
            *_linker_script_flags(setup.link.linker),
            # A memory test is checked through its `results` array,
            # which it may only declare (a test that just checks .bss
            # is zeroed never reads it). The toolchain's linker script
            # collects unreferenced sections (--gc-sections), so the
            # symbol is named as needed to keep it.
            *(
                ["-Wl,--undefined=results"]
                if kind == "memory" and c_file.suffix != ".S"
                else []
            ),
            *setup.link.link_flags,
            *([str(crt0)] if crt0 is not None else []),
            *sources,
            str(c_file),
            "-o",
            str(elf),
        ],
    )
    elf_to_bin(toolchain_cfg, elf, bin_)
    return bin_, march, kind, timeout_s


def _runtime_flags(
    toolchain_cfg: dict[str, Any], march: str, link: LinkSetup, cxx: bool
) -> list[str]:
    """Return the flags that choose the runtime a test links against.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section.
    march : str
        The `-march` value of the test.
    link : LinkSetup
        The startup file and linker script of the project, if any.
    cxx : bool
        True when the test is a C++ source.

    Returns
    -------
    list of str
        `--specs=<file>` with `toolchain.specs`; for C++ without it,
        the picolibc flags of `cxx_flags`; otherwise
        `-ffreestanding` and the flags of `libc_flags`.

    Raises
    ------
    ValueError
        A C++ source without `toolchain.cxx: true`, or with the
        project's own `crt0` (it would leave out the objects that
        register the unwind frames).
    CxxLibraryMissingError
        The toolchain has no `libstdc++` for the variant of the test.
    """
    specs = toolchain_cfg.get("specs")
    if cxx:
        if not cxx_enabled(toolchain_cfg):
            raise ValueError("a C++ source needs toolchain.cxx: true")
        if link.crt0 is not None:
            raise ValueError(
                "C++ cannot use paths.crt0: the startup of the toolchain "
                "registers the unwind frames"
            )
        require_libstdcxx(toolchain_cfg, march, abi_for(march))
    # A specs file describes a hosted platform: main() returns to the
    # crt0, which calls exit(), so the compiler must not be told the
    # program is freestanding (that also drops main's implicit return
    # 0).
    if specs:
        return [f"--specs={specs}"]
    if cxx:
        return cxx_flags(toolchain_cfg, own_linker=link.linker is not None)
    return ["-ffreestanding", *libc_flags(toolchain_cfg)]


def _compile_extras(
    setup: BuildSetup,
    march: str,
    runtime_flags: list[str],
    out_dir: Path,
) -> list[str]:
    """Compile the extra sources of a C++ test into objects, as C.

    Parameters
    ----------
    setup : BuildSetup
        The build settings; `link.extra_sources` is what is compiled.
    march : str
        The `-march` value of the test.
    runtime_flags : list of str
        The runtime flags of the test.
    out_dir : Path
        Directory for the objects (created if missing).

    Returns
    -------
    list of str
        The object files, in the order of the sources.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    objects: list[str] = []
    for index, source in enumerate(setup.link.extra_sources):
        obj = out_dir / f"{index}-{source.stem}.o"
        run_gcc(
            setup.toolchain_cfg,
            [
                *optimize_flags(march),
                *runtime_flags,
                f"-I{setup.include_dir}",
                *without_cxx_only_flags(setup.link.link_flags),
                "-c",
                str(source),
                "-o",
                str(obj),
            ],
        )
        objects.append(str(obj))
    return objects


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
