"""C++ on top of picolibc: which flags, which driver, which library.

`toolchain.cxx: true` (with `toolchain.libc: picolibc` or a
`toolchain.specs` file) lets a test be written in C++ (`src.cc` or
`src.cpp`). The test is compiled and linked by the `g++` driver, against
the `libstdc++` the toolchain carries for the ISA of the test.
"""

import functools
import os
import subprocess
from pathlib import Path
from typing import Any, cast

#: Suffixes of the sources compiled as C++.
CXX_SUFFIXES = (".cc", ".cpp")

#: The standard every C++ source is held to, with every diagnostic as an
#: error (the C++ counterpart of `build.C_STANDARD_FLAGS`).
#: Flags that only a C++ compile accepts: a C compile of the same line
#: stops at them, with every diagnostic an error.
CXX_ONLY_FLAGS = (
    "-std=",
    "-frtti",
    "-fno-rtti",
    "-fthreadsafe-statics",
    "-fno-threadsafe-statics",
    "-fuse-cxa-atexit",
    "-fno-use-cxa-atexit",
    "-fno-sized-deallocation",
    "-fcoroutines",
)

CXX_STANDARD_FLAGS = [
    "-std=c++23",
    "-Wall",
    "-Wextra",
    "-Wpedantic",
    "-Werror",
]

#: The linker script of picolibc for C++ (the C one is `picolibc.ld`).
CXX_LINKER_SCRIPT = "picolibcpp.ld"

#: The specs file of picolibc that links the start and end objects the
#: C++ runtime registers its unwind frames with.
CXX_SPECS = "picolibcpp.specs"

#: The library of the C++ runtime the link needs.
LIBSTDCXX = "libstdc++.a"


class CxxLibraryMissingError(ValueError):
    """The toolchain has no `libstdc++` for the variant of a test."""


def without_cxx_only_flags(flags: list[str]) -> list[str]:
    """Drop the flags a C compile refuses.

    Parameters
    ----------
    flags : list of str
        The extra gcc flags of a project.

    Returns
    -------
    list of str
        The flags without those of `CXX_ONLY_FLAGS`, which the C and
        assembly sources of a C++ test are compiled without.
    """
    return [flag for flag in flags if not flag.startswith(CXX_ONLY_FLAGS)]


def is_cxx_source(path: Path) -> bool:
    """Tell whether a source file is compiled as C++.

    Parameters
    ----------
    path : Path
        The source file.

    Returns
    -------
    bool
        True for `.cc` and `.cpp`.
    """
    return path.suffix in CXX_SUFFIXES


def cxx_enabled(toolchain_cfg: dict[str, Any]) -> bool:
    """Read `toolchain.cxx` and check it fits the rest of the section.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section.

    Returns
    -------
    bool
        The value of `cxx` (False when absent).

    Raises
    ------
    ValueError
        `cxx` is not a boolean, or is true without picolibc (`libc:
        picolibc`, or a `specs` file, which includes it).
    """
    cxx = toolchain_cfg.get("cxx", False)
    if not isinstance(cxx, bool):
        raise ValueError(f"toolchain.cxx must be true or false, got {cxx!r}")
    if cxx and not (
        toolchain_cfg.get("specs") or toolchain_cfg.get("libc") == "picolibc"
    ):
        raise ValueError(
            "toolchain.cxx needs toolchain.libc: picolibc "
            "(or a toolchain.specs file)"
        )
    return cxx


def cxx_options(toolchain_cfg: dict[str, Any]) -> list[str]:
    """Read `toolchain.cxx_options`, the extra flags of C++ sources.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section.

    Returns
    -------
    list of str
        The flags, such as `-fno-exceptions` and `-fno-rtti` for a
        smaller program. They go to the compile and the link of C++
        sources only (empty when absent).

    Raises
    ------
    ValueError
        `cxx_options` is not a list of strings.
    """
    options = cast("object", toolchain_cfg.get("cxx_options") or [])
    if not isinstance(options, list) or not all(
        isinstance(option, str) for option in cast("list[object]", options)
    ):
        raise ValueError("toolchain.cxx_options must be a list of strings")
    return list(cast("list[str]", options))


def gxx_for(toolchain_cfg: dict[str, Any]) -> str:
    """Name the `g++` driver of the toolchain.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; `gxx` names it
        outright, otherwise it is `gcc` with its `gcc` ending turned
        into `g++`.

    Returns
    -------
    str
        The binary name or path.

    Raises
    ------
    ValueError
        No `gxx`, and `gcc` does not end in `gcc`.
    """
    named = toolchain_cfg.get("gxx")
    if named:
        return str(named)
    gcc = str(toolchain_cfg["gcc"])
    if not gcc.endswith("gcc"):
        raise ValueError(
            f"cannot derive the g++ of {gcc!r}: set toolchain.gxx"
        )
    return gcc.removesuffix("gcc") + "g++"


def cxx_flags(
    toolchain_cfg: dict[str, Any], own_linker: bool = False
) -> list[str]:
    """Return the flags of a C++ link with the toolchain's own startup.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section.
    own_linker : bool
        True when the project passes its own linker script.

    Returns
    -------
    list of str
        `--specs=picolibcpp.specs`, which keeps `--crt0=` and links
        `crtbegin.o` and `crtend.o` (they register the unwind frames),
        `--crt0=hosted` (so `main` returning calls `exit`),
        `--no-gc-sections`, as the C flags of picolibc do, and the
        linker script of picolibc for C++ unless `own_linker`.
    """
    del toolchain_cfg
    return [
        f"--specs={CXX_SPECS}",
        "--crt0=hosted",
        "-Wl,--no-gc-sections",
        *([] if own_linker else ["-T", CXX_LINKER_SCRIPT]),
    ]


@functools.cache
def _driver_answer(gcc: str, march: str, abi: str, query: str) -> str:
    """Ask the driver a `-print-*` question for a variant.

    Parameters
    ----------
    gcc : str
        The gcc binary.
    march : str
        The `-march` value.
    abi : str
        The `-mabi` value.
    query : str
        The option that asks, such as `-print-multi-directory`.

    Returns
    -------
    str
        What the driver prints, stripped.
    """
    done = subprocess.run(
        [
            gcc,
            f"-march={march}",
            f"-mabi={abi}",
            "--specs=picolibc.specs",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def library_is_of_variant(found: str, multidir: str) -> bool:
    """Tell whether a `libstdc++.a` found is the one of the variant.

    The driver looks for a library in the folder of the variant first
    and then in every other folder, so a toolchain built with
    `libstdc++` for the default variant only still prints a path for
    any other, and that library would link the wrong code.

    Parameters
    ----------
    found : str
        What `-print-file-name=libstdc++.a` printed: a path, or the bare
        name when the driver finds nothing.
    multidir : str
        What `-print-multi-directory` printed: the folder of the
        variant under the library folder, `.` for the default one.

    Returns
    -------
    bool
        True when the file exists and sits in the folder of the variant.
    """
    if not found or found == LIBSTDCXX:
        return False
    path = Path(os.path.normpath(found))
    if not path.is_file():
        return False
    return multidir in ("", ".") or path.parent.as_posix().endswith(multidir)


def require_libstdcxx(
    toolchain_cfg: dict[str, Any], march: str, abi: str
) -> None:
    """Fail clearly when the toolchain has no `libstdc++` for a variant.

    Parameters
    ----------
    toolchain_cfg : dict of {str: Any}
        The project's `toolchain:` config section; needs `gcc`.
    march : str
        The `-march` value of the test.
    abi : str
        The `-mabi` value of the test.

    Raises
    ------
    CxxLibraryMissingError
        The driver does not find `libstdc++.a` for `march` and `abi`.
        The toolchain must be built with it for that variant (a C++
        source of it would otherwise stop at `cannot find -lstdc++`, or
        at a missing `bits/c++config.h`).
    """
    gcc = str(toolchain_cfg["gcc"])
    found = _driver_answer(gcc, march, abi, f"-print-file-name={LIBSTDCXX}")
    multidir = _driver_answer(gcc, march, abi, "-print-multi-directory")
    if not library_is_of_variant(found, multidir):
        raise CxxLibraryMissingError(
            f"toolchain.cxx is true but the toolchain has no {LIBSTDCXX} "
            f"for the variant -march={march} -mabi={abi} "
            f"(folder {multidir}): the toolchain must be built with "
            f"libstdc++ for it"
        )
