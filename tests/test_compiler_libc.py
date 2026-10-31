"""Tests for compiler_libc."""

import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.compiler import (
    BuildSetup,
    LinkSetup,
    compile_test,
    libc_flags,
)

GCC = "riscv32-unknown-elf-gcc"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "htif_min"
ISA = {"base": "i", "default_ext": "", "canonical_order": "MAFDQLCBJTPVNH"}


def _has_picolibc() -> bool:
    if shutil.which(GCC) is None:
        return False
    probe = subprocess.run(
        [
            GCC,
            "--specs=picolibc.specs",
            "-E",
            "-x",
            "c",
            "/dev/null",
            "-o",
            "/dev/null",
        ],
        check=False,
        capture_output=True,
    )
    return probe.returncode == 0


needs_picolibc = pytest.mark.skipif(
    not _has_picolibc(), reason=f"needs a {GCC} configured with picolibc"
)


def test_libc_flags_defaults_to_no_libc() -> None:
    """Libc flags defaults to no libc."""
    assert libc_flags({}) == ["-nostdlib"]


def test_libc_flags_picolibc_keeps_sections_the_script_does_not_reach() -> (
    None
):
    """Libc flags picolibc keeps sections the script does not reach."""
    assert libc_flags({"libc": "picolibc"}) == [
        "--specs=picolibc.specs",
        "-Wl,--no-gc-sections",
    ]


def test_libc_flags_rejects_an_unknown_library() -> None:
    """Libc flags rejects an unknown library."""
    with pytest.raises(ValueError, match=r"toolchain\.libc"):
        libc_flags({"libc": "glibc"})


def _compile(tmp_path: Path, libc: str) -> Path:
    src = tmp_path / "src.c"
    src.write_text(
        "#include <string.h>\n"
        'volatile const char *volatile text = "riscv";\n'
        "volatile unsigned int result;\n"
        "int main(void) {\n"
        "    result = (unsigned int)strlen((const char *)text);\n"
        "    return 0;\n"
        "}\n"
    )
    setup = BuildSetup(
        toolchain_cfg={
            "gcc": GCC,
            "objcopy": "riscv32-unknown-elf-objcopy",
            "libc": libc,
        },
        isa_cfg=ISA,
        default_timeout_s=5.0,
        include_dir=tmp_path,
        link=LinkSetup(crt0=FIXTURES / "crt0.S", linker=FIXTURES / "link.ld"),
    )
    bin_, _march, _kind, _timeout = compile_test(
        setup, src, "strlen_test", tmp_path / "build"
    )
    return bin_


@needs_picolibc
def test_picolibc_provides_libc_functions(tmp_path: Path) -> None:
    """Picolibc provides libc functions."""
    assert _compile(tmp_path, "picolibc").is_file()


@needs_picolibc
def test_no_libc_leaves_libc_functions_undefined(tmp_path: Path) -> None:
    """No libc leaves libc functions undefined."""
    with pytest.raises(subprocess.CalledProcessError):
        _compile(tmp_path, "none")
