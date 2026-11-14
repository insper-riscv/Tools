"""Tests for the C++ support of the compiler (none needs a GCC)."""

import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import ISA, check, check_equal, check_false, check_in

from riscv_tools.cli import discover_tests
from riscv_tools.compiler import (
    BuildSetup,
    CxxLibraryMissingError,
    LinkSetup,
    compile_test,
    cxx_enabled,
    cxx_flags,
    cxx_options,
    gxx_for,
    is_cxx_source,
    require_libstdcxx,
)
from riscv_tools.compiler.cxx import (
    library_is_of_variant,
    without_cxx_only_flags,
)

PICOLIBC = {"gcc": "riscv32-unknown-elf-gcc", "libc": "picolibc"}


def test_cxx_defaults_to_off() -> None:
    """Without `cxx` the C++ support is off."""
    check_false(cxx_enabled({}))
    check_false(cxx_enabled({"libc": "picolibc"}))


def test_cxx_with_picolibc_is_on() -> None:
    """`cxx: true` with picolibc turns the C++ support on."""
    check(cxx_enabled({**PICOLIBC, "cxx": True}))


def test_cxx_with_a_specs_file_is_on() -> None:
    """`cxx: true` with a specs file turns the C++ support on."""
    check(cxx_enabled({"specs": "p.specs", "cxx": True}))


def test_cxx_without_picolibc_is_refused() -> None:
    """C++ has no libc to stand on with `libc: none`."""
    with pytest.raises(ValueError, match=r"toolchain\.cxx needs"):
        cxx_enabled({"libc": "none", "cxx": True})


def test_cxx_must_be_a_boolean() -> None:
    """A string is not a switch."""
    with pytest.raises(ValueError, match="true or false"):
        cxx_enabled({**PICOLIBC, "cxx": "yes"})


def test_the_gxx_is_the_gcc_with_the_name_changed() -> None:
    """The `g++` of a toolchain is derived from its `gcc`."""
    check_equal(
        gxx_for({"gcc": "riscv32-unknown-elf-gcc"}), "riscv32-unknown-elf-g++"
    )
    check_equal(
        gxx_for({"gcc": "/opt/x/bin/riscv64-unknown-elf-gcc"}),
        "/opt/x/bin/riscv64-unknown-elf-g++",
    )


def test_the_gxx_can_be_named() -> None:
    """`toolchain.gxx` wins over the derived name."""
    check_equal(gxx_for({"gcc": "cc", "gxx": "my-g++"}), "my-g++")


def test_the_gxx_cannot_be_derived_from_a_odd_name() -> None:
    """A gcc that does not end in `gcc` needs `toolchain.gxx`."""
    with pytest.raises(ValueError, match=r"toolchain\.gxx"):
        gxx_for({"gcc": "cc"})


def test_cxx_sources_are_cc_and_cpp() -> None:
    """Only `.cc` and `.cpp` are compiled as C++."""
    check(is_cxx_source(Path("src.cc")))
    check(is_cxx_source(Path("src.cpp")))
    check_false(is_cxx_source(Path("src.c")))
    check_false(is_cxx_source(Path("src.S")))


def test_cxx_flags_use_the_cpp_specs_and_linker_script() -> None:
    """The flags link the unwind objects and the C++ linker script."""
    flags = cxx_flags(PICOLIBC)
    check_in("--specs=picolibcpp.specs", flags)
    check_in("--crt0=hosted", flags)
    check_equal(flags[-2:], ["-T", "picolibcpp.ld"])


def test_cxx_flags_leave_a_project_linker_script_alone() -> None:
    """With a linker script of its own the project picks it."""
    check_false("-T" in cxx_flags(PICOLIBC, own_linker=True))


def _library(tmp_path: Path, folder: str) -> str:
    """Make a `libstdc++.a` in a folder and return a path to it."""
    path = tmp_path / "lib" / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "libstdc++.a").write_text("")
    # The driver prints the path with a detour through `..`.
    return str(tmp_path / "gcc" / ".." / "lib" / folder / "libstdc++.a")


def test_the_library_of_the_variant_is_accepted(tmp_path: Path) -> None:
    """The file in the folder of the variant is the library."""
    check(
        library_is_of_variant(_library(tmp_path, "rv32i/ilp32"), "rv32i/ilp32")
    )


def test_the_library_of_the_default_variant_is_accepted(
    tmp_path: Path,
) -> None:
    """The default variant has no folder of its own."""
    check(library_is_of_variant(_library(tmp_path, "."), "."))


def test_the_library_of_another_variant_is_refused(tmp_path: Path) -> None:
    """The driver falls back to the default folder, not the variant."""
    found = _library(tmp_path, ".")
    check_false(library_is_of_variant(found, "rv32ima_zaamo_zalrsc/ilp32"))


def test_a_bare_name_means_the_library_is_missing(tmp_path: Path) -> None:
    """The driver prints the bare name when it finds nothing."""
    check_false(library_is_of_variant("libstdc++.a", "."))
    check_false(library_is_of_variant("", "."))
    check_false(library_is_of_variant(str(tmp_path / "libstdc++.a"), "."))


def _fake_gcc(tmp_path: Path, found: str, multidir: str) -> dict[str, Any]:
    """Write a gcc that answers the two questions, return its config."""
    script = tmp_path / "fake-gcc"
    script.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        f"    -print-file-name=*) echo '{found}' ;;\n"
        f"    -print-multi-directory) echo '{multidir}' ;;\n"
        "  esac\n"
        "done\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {"gcc": str(script), "libc": "picolibc", "cxx": True}


def test_a_variant_without_the_library_is_refused_by_name(
    tmp_path: Path,
) -> None:
    """The message names the variant and says the toolchain needs it."""
    cfg = _fake_gcc(tmp_path, "libstdc++.a", "rv32ima_zaamo_zalrsc/ilp32")
    with pytest.raises(CxxLibraryMissingError) as error:
        require_libstdcxx(cfg, "rv32ima", "ilp32")
    message = str(error.value)
    check_in("-march=rv32ima -mabi=ilp32", message)
    check_in("libstdc++.a", message)
    check_in("built with libstdc++", message)


def test_a_variant_with_the_library_passes(tmp_path: Path) -> None:
    """A toolchain that has the library raises nothing."""
    found = _library(tmp_path, "rv32im_zmmul/ilp32")
    cfg = _fake_gcc(tmp_path, found, "rv32im_zmmul/ilp32")
    require_libstdcxx(cfg, "rv32im", "ilp32")


def _setup(
    tmp_path: Path, cfg: dict[str, Any], link: LinkSetup | None = None
) -> BuildSetup:
    return BuildSetup(
        toolchain_cfg={"objcopy": "objcopy", **cfg},
        isa_cfg=ISA,
        default_timeout_s=5.0,
        include_dir=tmp_path,
        link=link or LinkSetup(),
    )


def _source(tmp_path: Path, name: str = "src.cc") -> Path:
    path = tmp_path / name
    path.write_text("int main() { return 0; }\n")
    return path


def test_a_cxx_source_needs_cxx_on(tmp_path: Path) -> None:
    """A `.cc` without `toolchain.cxx` stops before the compiler."""
    setup = _setup(
        tmp_path, {"gcc": "riscv32-unknown-elf-gcc", "libc": "picolibc"}
    )
    with pytest.raises(ValueError, match=r"needs toolchain\.cxx: true"):
        compile_test(setup, _source(tmp_path), "t", tmp_path / "build")


def test_a_cxx_source_refuses_a_project_crt0(tmp_path: Path) -> None:
    """A crt0 of the project would drop the unwind frame objects."""
    setup = _setup(
        tmp_path,
        {"gcc": "riscv32-unknown-elf-gcc", "libc": "picolibc", "cxx": True},
        LinkSetup(crt0=tmp_path / "crt0.S"),
    )
    with pytest.raises(ValueError, match=r"paths\.crt0"):
        compile_test(setup, _source(tmp_path), "t", tmp_path / "build")


def test_a_cxx_source_without_the_library_stops_clearly(
    tmp_path: Path,
) -> None:
    """The refusal comes before the compile, with the variant named."""
    cfg = _fake_gcc(tmp_path, "libstdc++.a", ".")
    setup = _setup(tmp_path, cfg)
    with pytest.raises(CxxLibraryMissingError, match="rv32i"):
        compile_test(setup, _source(tmp_path), "t", tmp_path / "build")


def test_discovery_finds_cc_and_cpp_tests(tmp_path: Path) -> None:
    """A C++ test is a folder with a `src.cc` or a `src.cpp`."""
    for name, source in (("a", "src.c"), ("b", "src.cc"), ("c", "src.cpp")):
        (tmp_path / "c" / name).mkdir(parents=True)
        (tmp_path / "c" / name / source).write_text("")
    (tmp_path / "asm").mkdir()
    cfg = yaml.safe_load(
        yaml.safe_dump({"paths": {"c_dir": "c", "asm_dir": "asm"}})
    )

    found = discover_tests(tmp_path, cfg)

    check_equal([p.name for p in found], ["src.c", "src.cc", "src.cpp"])


def test_c_extras_drop_the_flags_only_cpp_takes() -> None:
    """A C compile with `-fno-rtti` stops, so the flag stays off it."""
    flags = ["-DX=1", "-fno-rtti", "-fno-exceptions", "-std=c++26"]
    check_equal(without_cxx_only_flags(flags), ["-DX=1", "-fno-exceptions"])


def test_cxx_options_default_to_none() -> None:
    """Without `cxx_options` a C++ source gets no extra flag."""
    check_equal(cxx_options({}), [])


def test_cxx_options_are_read_as_given() -> None:
    """The flags come out in the order they were written."""
    cfg = {"cxx_options": ["-fno-exceptions", "-fno-rtti"]}
    check_equal(cxx_options(cfg), ["-fno-exceptions", "-fno-rtti"])


def test_cxx_options_must_be_a_list_of_strings() -> None:
    """A bare string would be read as letters: it is refused."""
    with pytest.raises(ValueError, match="list of strings"):
        cxx_options({"cxx_options": "-fno-rtti"})
