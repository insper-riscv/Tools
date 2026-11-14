"""End-to-end tests of C++ programs on picolibc, run in Spike.

They need a GCC configured with picolibc whose toolchain also carries
`libstdc++` for `rv32i` and `rv32im` (the `ci-elf` image of the Infra
repository, with C++), and Spike. The specs file and the system
calls come from the generator, as a project gets them.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from support import (
    GCC,
    ISA,
    check_equal,
    dump_platform,
    has_picolibc,
)

from riscv_tools.compiler import (
    BuildSetup,
    CxxLibraryMissingError,
    LinkSetup,
    compile_test,
    gxx_for,
    require_libstdcxx,
)
from riscv_tools.memory_map import write_all

NM = "riscv32-unknown-elf-nm"
SPIKE = "spike"
RUNTIME = (
    Path(__file__).resolve().parent / "fixtures" / "cxx_min" / "runtime.c"
)

PLATFORM: dict[str, Any] = {
    "regions": [
        {"name": "BOOT_MEMORY", "base": "0x0", "size": "2K", "exec": True},
        {"name": "FLASH", "base": "0x800", "size": "1022K", "exec": True},
        {"name": "RAM", "base": "0x100000", "size": "1024K", "kind": "ram"},
    ],
    "reserved": {
        "stdout": {"base": "0x1FFBE0", "size": "1K+8"},
        "tohost": {"base": "0x1FFFE8", "size": "8"},
        "fromhost": {"base": "0x1FFFF0", "size": "8"},
    },
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "generate": {
        "specs": {
            "path": "out/cxx.specs",
            "rom": "FLASH",
            "ram": "RAM",
            "ram_limit": "stdout",
            "cxx": True,
        },
        "syscalls": {"path": "out/syscalls.c"},
    },
}

# Every program returns 0 when it behaves as C++ must, and a code that
# says what failed otherwise: _exit hands it to Spike.
PROGRAMS: dict[str, str] = {
    "global_constructor": """\
static int value;
struct Global {
    Global() { value = 7; }
};
static Global global;
int main() { return value == 7 ? 0 : 1; }
""",
    "virtual_new_delete": """\
static int live;
struct Base {
    Base() { ++live; }
    virtual ~Base() { --live; }
    virtual int f() const { return 1; }
};
struct Derived : Base {
    int f() const override { return 7; }
};
int main() {
    Base *p = new Derived;
    const int during = live;
    const int r = p->f();
    delete p;
    return (r == 7 && during == 1 && live == 0) ? 0 : 1;
}
""",
    "array_vector": """\
#include <array>
#include <vector>
int main() {
    std::array<int, 4> a{1, 2, 3, 4};
    std::vector<int> v;
    for (int i = 0; i < 100; ++i) v.push_back(i);
    int sum = 0;
    for (int x : v) sum += x;
    for (int x : a) sum += x;
    return sum == 4950 + 10 ? 0 : 1;
}
""",
    "throw_catch": """\
static int destroyed;
struct Guard {
    ~Guard() { ++destroyed; }
};
static void thrower() {
    Guard a;
    Guard b;
    throw 42;
}
int main() {
    int caught = 0;
    try {
        thrower();
    } catch (int e) {
        caught = e;
    }
    return (caught == 42 && destroyed == 2) ? 0 : 1;
}
""",
    "no_exceptions": """\
static int live;
struct Base {
    Base() { ++live; }
    virtual ~Base() { --live; }
    virtual int f() const { return 1; }
};
struct Derived : Base {
    int f() const override { return 7; }
};
int main() {
    Base *p = new Derived;
    const int r = p->f();
    delete p;
    return (r == 7 && live == 0) ? 0 : 1;
}
""",
}

# The memory map of the generated specs file, for a link without it.
DEFSYMS = [
    "-Wl,--defsym=__flash=0x800",
    "-Wl,--defsym=__flash_size=0xFF800",
    "-Wl,--defsym=__ram=0x100000",
    "-Wl,--defsym=__ram_size=0xFFBE0",
]

VARIANTS = {"rv32i": "", "rv32im": "// RV32_EXT: M\n"}


def _has_libstdcxx(march: str) -> bool:
    """Tell whether the GCC on PATH has libstdc++ for a variant."""
    try:
        require_libstdcxx({"gcc": GCC}, march, "ilp32")
    except CxxLibraryMissingError, subprocess.CalledProcessError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not has_picolibc()
    or shutil.which(gxx_for({"gcc": GCC})) is None
    or shutil.which(SPIKE) is None
    or not _has_libstdcxx("rv32i")
    or not _has_libstdcxx("rv32im"),
    reason=f"needs {GCC} with picolibc and libstdc++, g++ and {SPIKE}",
)


def _entry(elf: Path) -> int:
    """Read the address of `_start`."""
    out = subprocess.run(
        [NM, str(elf)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        fields = line.split()
        if fields[-1] == "_start":
            return int(fields[0], 16)
    raise AssertionError("no _start in the ELF")


def _run(
    tmp_path: Path,
    name: str,
    variant: str,
    *flags: str,
    own_specs: bool = True,
) -> int:
    """Compile a program with the generated files, run it in Spike.

    With `own_specs` false the program links through `picolibcpp.specs`
    and the memory map comes from `--defsym` flags, not the generated
    specs file.
    """
    (tmp_path / "platform.yaml").write_text(dump_platform(PLATFORM))
    write_all(tmp_path / "platform.yaml", tmp_path)
    src = tmp_path / name / "src.cc"
    src.parent.mkdir()
    src.write_text(VARIANTS[variant] + PROGRAMS[name])
    setup = BuildSetup(
        toolchain_cfg={
            "gcc": GCC,
            "objcopy": "riscv32-unknown-elf-objcopy",
            "libc": "picolibc",
            "cxx": True,
            "cxx_options": list(flags),
            **(
                {"specs": str(tmp_path / "out" / "cxx.specs")}
                if own_specs
                else {}
            ),
        },
        isa_cfg=ISA,
        default_timeout_s=5.0,
        include_dir=tmp_path,
        link=LinkSetup(
            extra_sources=[RUNTIME, tmp_path / "out" / "syscalls.c"],
            link_flags=[] if own_specs else DEFSYMS,
        ),
    )
    compile_test(setup, src, f"{name}_{variant}", tmp_path / "build")
    elf = tmp_path / "build" / f"{name}_{variant}.elf"
    done = subprocess.run(
        [
            SPIKE,
            "--isa=rv32im",
            "-m0x0:0x200000",
            "--disable-dtb",
            f"--pc={_entry(elf):#x}",
            str(elf),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return done.returncode


@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize(
    "name", ["global_constructor", "virtual_new_delete", "array_vector"]
)
def test_cxx_programs_run(tmp_path: Path, name: str, variant: str) -> None:
    """Constructors, virtual calls, new and delete, the containers."""
    check_equal(_run(tmp_path, name, variant), 0)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_throw_and_catch_run_the_destructors(
    tmp_path: Path, variant: str
) -> None:
    """The unwinder finds the frames the startup objects register."""
    check_equal(_run(tmp_path, "throw_catch", variant), 0)


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_no_exceptions_no_rtti_runs(tmp_path: Path, variant: str) -> None:
    """The size-saving flags still link and run."""
    check_equal(
        _run(
            tmp_path, "no_exceptions", variant, "-fno-exceptions", "-fno-rtti"
        ),
        0,
    )


def test_a_variant_without_libstdcxx_is_refused() -> None:
    """The toolchain may lack one: the message names it."""
    if _has_libstdcxx("rv32ima"):
        pytest.skip("this toolchain has libstdc++ for rv32ima as well")
    with pytest.raises(CxxLibraryMissingError, match="rv32ima"):
        require_libstdcxx({"gcc": GCC}, "rv32ima", "ilp32")


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_cxx_links_without_a_specs_file(tmp_path: Path, variant: str) -> None:
    """`libc: picolibc` with `cxx` alone catches an exception too."""
    check_equal(
        _run(tmp_path, "throw_catch", variant, own_specs=False),
        0,
    )
