import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.compiler import compile_test, libc_flags

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
    assert libc_flags({}) == ["-nostdlib"]


def test_libc_flags_picolibc_keeps_sections_the_link_script_does_not_reach() -> None:
    assert libc_flags({"libc": "picolibc"}) == [
        "--specs=picolibc.specs",
        "-Wl,--no-gc-sections",
    ]


def test_libc_flags_rejects_an_unknown_library() -> None:
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
    bin_, _march, _kind, _timeout = compile_test(
        {"gcc": GCC, "objcopy": "riscv32-unknown-elf-objcopy", "libc": libc},
        ISA,
        5.0,
        src,
        "strlen_test",
        tmp_path / "build",
        tmp_path,
        FIXTURES / "crt0.S",
        FIXTURES / "link.ld",
    )
    return bin_


@needs_picolibc
def test_picolibc_provides_libc_functions(tmp_path: Path) -> None:
    assert _compile(tmp_path, "picolibc").is_file()


@needs_picolibc
def test_no_libc_leaves_libc_functions_undefined(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        _compile(tmp_path, "none")
