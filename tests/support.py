"""Helpers shared by the test modules."""

import argparse
import json
import shutil
import struct
import subprocess
from collections.abc import Container, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from riscv_tools import cli
from riscv_tools.htif import write_header
from riscv_tools.memory_map import set_override
from riscv_tools.memory_map.core_profile import legacy_to_core

GCC = "riscv32-unknown-elf-gcc"
OBJCOPY = "riscv32-unknown-elf-objcopy"
_ELFCLASS32 = 1
_ELFDATA2LSB = 1
_PHOFF, _PHENTSIZE, _SHENTSIZE = 52, 32, 40
ISA = {"base": "i", "default_ext": "", "canonical_order": "MAFDQLCBJTPVNH"}

# The regions and the reserved words of a small platform map, shared by
# the tests of the files that are generated from a map.
MAP_REGIONS: list[dict[str, Any]] = [
    {"name": "BOOT_MEMORY", "base": "0x0", "size": "2K", "exec": True},
    {"name": "FLASH", "base": "0x800", "size": "30K", "exec": True},
    {"name": "RAM", "base": "0x8000", "size": "160K", "kind": "ram"},
]
MAP_RESERVED: dict[str, Any] = {
    "stdout": {"base": "0x2FBE0", "size": "1K+8"},
    "tohost": {"base": "0x2FFE8", "size": "8"},
    "fromhost": {"base": "0x2FFF0", "size": "8"},
}


def profile_matrix(*bases: str) -> dict[str, Any]:
    """Build a profile specification with the given base names.

    The extensions are Zicsr, Zicntr (which implies Zicsr) and M, and
    a base whose name ends in `e` sets `has_e`.
    """
    extensions: list[dict[str, Any]] = [
        {"name": "Zicclsm", "generic": "has_zicclsm"},
        {"name": "Zicsr", "generic": "has_zicsr"},
        {"name": "Zicntr", "generic": "has_zicntr", "implies": ["has_zicsr"]},
        {"name": "M", "generic": "has_m", "base_letter": "m"},
    ]
    return {
        "bases": [
            {"name": name, "generics": {"has_e": name.endswith("e")}}
            for name in bases
        ],
        "extensions": extensions,
        "mutually_exclusive": [["Zicsr", "Zicntr"]],
    }


C_ADD_SOURCE = (
    '#include "rv32_test.h"\n'
    "int main(void) {\n"
    "    if (6 * 7 == 42) { RV32_PASS(); }\n"
    "    RV32_FAIL();\n"
    "    return 0;\n"
    "}\n"
)
C_MEM_SOURCE = (
    "// RV32_TEST_KIND: memory\n"
    '#include "rv32_test.h"\n'
    "volatile unsigned int results[1];\n"
    "int main(void) {\n"
    "    results[0] = 0x11111111u;\n"
    "    RV32_PASS();\n"
    "    return 0;\n"
    "}\n"
)


def has_picolibc() -> bool:
    """Tell whether the gcc on PATH was configured with picolibc."""
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


def link_bare(
    sources: Sequence[Path],
    ld: Path,
    elf: Path,
    *,
    march: str = "rv32im",
    flags: Sequence[str] = (),
) -> None:
    """Link sources with the script ld into elf, without a libc."""
    subprocess.run(
        [
            GCC,
            f"-march={march}",
            "-mabi=ilp32",
            *flags,
            "-nostdlib",
            "-nostartfiles",
            "-T",
            str(ld),
            *map(str, sources),
            "-o",
            str(elf),
        ],
        check=True,
    )


def write_c_test(root: Path, name: str, source: str) -> None:
    """Write c/<name>/src.c under root."""
    directory = root / "c" / name
    directory.mkdir(parents=True)
    (directory / "src.c").write_text(source, encoding="utf-8")


def toolchain_section(**extra: Any) -> dict[str, Any]:
    """Return the `toolchain:` config of the tests, plus extra keys."""
    return {"gcc": GCC, "objcopy": OBJCOPY, **extra}


def write_config(root: Path, config: dict[str, Any]) -> None:
    """Write config as root/config.yaml."""
    (root / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def compile_args(
    root: Path, emit: str, only: str | list[str] | None = None
) -> argparse.Namespace:
    """Build the parsed arguments of `riscv-tools compile`."""
    args = argparse.Namespace(
        config=str(root / "config.yaml"),
        manifest=None,
        manifest_per_test=None,
        root=str(root),
        emit=emit,
    )
    if only is not None:
        args.only = only
    return args


def _symbol_tables(symbols: dict[str, int]) -> tuple[bytes, bytes]:
    """Build the ELF .symtab and .strtab contents for symbols."""
    names = b"\0" + b"".join(n.encode() + b"\0" for n in symbols)
    offsets: dict[str, int] = {}
    pos = 1
    for n in symbols:
        offsets[n] = pos
        pos += len(n) + 1
    symtab = bytes(16) + b"".join(
        struct.pack("<IIIBBH", offsets[n], v, 4, 0, 0, 1)
        for n, v in symbols.items()
    )
    return symtab, names


def _elf_header(shoff: int, phnum: int) -> bytes:
    """Build the 52-byte header of a little-endian 32-bit RISC-V ELF."""
    header = bytearray(52)
    header[:4] = b"\x7fELF"
    header[4], header[5] = _ELFCLASS32, _ELFDATA2LSB
    struct.pack_into(
        "<HHIIIIIHHHHHH",
        header,
        16,
        2,
        0xF3,
        1,
        0,
        _PHOFF,
        shoff,
        0,
        52,
        _PHENTSIZE,
        phnum,
        _SHENTSIZE,
        3,
        0,
    )
    return bytes(header)


def _program_headers(
    segments: list[tuple[int, bytes]], seg_offsets: list[int]
) -> bytes:
    """Build one PT_LOAD program header per segment."""
    return b"".join(
        struct.pack(
            "<IIIIIIII", 1, off, addr, addr, len(data), len(data), 7, 4
        )
        for (addr, data), off in zip(segments, seg_offsets, strict=True)
    )


def build_elf(
    segments: list[tuple[int, bytes]], symbols: dict[str, int] | None = None
) -> bytes:
    """Build a 32-bit ELF with PT_LOAD segments and a symbol table."""
    symtab, names = _symbol_tables(symbols or {})
    body = bytearray()
    seg_offsets: list[int] = []
    base = _PHOFF + _PHENTSIZE * len(segments)
    for _, data in segments:
        seg_offsets.append(base + len(body))
        body += data
    symtab_off = base + len(body)
    body += symtab
    names_off = base + len(body)
    body += names
    sections = bytes(_SHENTSIZE)
    sections += struct.pack(
        "<IIIIIIIIII", 0, 2, 0, 0, symtab_off, len(symtab), 2, 0, 4, 16
    )
    sections += struct.pack(
        "<IIIIIIIIII", 0, 3, 0, 0, names_off, len(names), 0, 0, 1, 0
    )
    return (
        _elf_header(base + len(body), len(segments))
        + _program_headers(segments, seg_offsets)
        + bytes(body)
        + sections
    )


def write_rv32_header(root: Path, tohost_addr: int) -> None:
    """Write include/rv32_test.h, with tohost at tohost_addr."""
    include_dir = root / "include"
    include_dir.mkdir()
    write_header(tohost_addr, include_dir / "rv32_test.h")


def write_zicsr_platform(
    base: Path, platform: dict[str, Any], **changes: Any
) -> Path:
    """Write a Zicsr matrix and the platform with ``changes``."""
    spec = {
        "bases": [{"name": "rv32i", "generics": {"num_regs": 32}}],
        "extensions": [{"name": "Zicsr", "generic": "has_zicsr"}],
    }
    (base / "matrix.yaml").write_text(yaml.safe_dump(spec))
    merged = yaml.safe_load(yaml.safe_dump(platform)) | changes
    path = base / "platform.yaml"
    path.write_text(dump_platform(merged))
    set_override(None)
    return path


def run_check_tree_main(
    monkeypatch: pytest.MonkeyPatch, root: Path, kind: str, only: str
) -> None:
    """Run ``riscv-tools check-tree`` as the command line does."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "riscv-tools",
            "--root",
            str(root),
            "check-tree",
            "--kind",
            kind,
            "--only",
            only,
        ],
    )
    cli.main()


def check(condition: object, message: str = "") -> None:
    """Fail the test unless the condition is true.

    Parameters
    ----------
    condition : object
        The value that must be truthy.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the condition is falsy.
    """
    if not condition:
        raise AssertionError(
            message or f"expected a true value: {condition!r}"
        )


def check_false(condition: object, message: str = "") -> None:
    """Fail the test unless the condition is false.

    Parameters
    ----------
    condition : object
        The value that must be falsy.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the condition is truthy.
    """
    if condition:
        raise AssertionError(
            message or f"expected a false value: {condition!r}"
        )


def check_equal(actual: object, expected: object, message: str = "") -> None:
    """Fail the test unless the two values are equal.

    Parameters
    ----------
    actual : object
        The value the code under test produced.
    expected : object
        The value it must equal.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the values differ.
    """
    if actual != expected:
        raise AssertionError(message or f"{actual!r} != {expected!r}")


def check_not_equal(actual: object, other: object, message: str = "") -> None:
    """Fail the test unless the two values differ.

    Parameters
    ----------
    actual : object
        The value the code under test produced.
    other : object
        The value it must differ from.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the values are equal.
    """
    if actual == other:
        raise AssertionError(message or f"{actual!r} == {other!r}")


def check_in(
    item: object, container: Container[Any], message: str = ""
) -> None:
    """Fail the test unless the item is in the container.

    Parameters
    ----------
    item : object
        The member to look for.
    container : Container of Any
        The collection that must hold it.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the item is missing.
    """
    if item not in container:
        raise AssertionError(message or f"{item!r} not in {container!r}")


def check_not_in(
    item: object, container: Container[Any], message: str = ""
) -> None:
    """Fail the test unless the item is absent from the container.

    Parameters
    ----------
    item : object
        The member that must be absent.
    container : Container of Any
        The collection that must not hold it.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If the item is present.
    """
    if item in container:
        raise AssertionError(message or f"{item!r} in {container!r}")


def check_is(actual: object, expected: object, message: str = "") -> None:
    """Fail the test unless the two names refer to the same object.

    Parameters
    ----------
    actual : object
        The value the code under test produced.
    expected : object
        The object it must be.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If they are different objects.
    """
    if actual is not expected:
        raise AssertionError(message or f"{actual!r} is not {expected!r}")


def check_is_not(actual: object, other: object, message: str = "") -> None:
    """Fail the test unless the two names refer to different objects.

    Parameters
    ----------
    actual : object
        The value the code under test produced.
    other : object
        The object it must not be.
    message : str, optional
        The failure message.

    Raises
    ------
    AssertionError
        If they are the same object.
    """
    if actual is other:
        raise AssertionError(message or f"{actual!r} is {other!r}")


def require_str(value: str | None, message: str = "") -> str:
    """Return the string after failing the test if it is None.

    Parameters
    ----------
    value : str or None
        The string that must be present.
    message : str, optional
        The failure message.

    Returns
    -------
    str
        The string, narrowed to not None.

    Raises
    ------
    AssertionError
        If the value is None.
    """
    if value is None:
        raise AssertionError(message or "expected a value, got None")
    return value


def read_manifest(project: Path, flavor: str) -> list[dict[str, Any]]:
    """Read the manifest a compile wrote under the build folder.

    Parameters
    ----------
    project : Path
        The project root.
    flavor : str
        The build subfolder, such as `real` or `sim`.

    Returns
    -------
    list of dict of str to Any
        The manifest entries.
    """
    path = project / "build" / flavor / "manifest.json"
    return json.loads(path.read_text())


def dump_platform(platform: dict[str, Any]) -> str:
    """Write a platform as YAML, with the `core` block.

    The tests describe a platform by a profile name and extras, and the
    file that the Tools read has the `core` block that stands for them.
    """
    data = dict(platform)
    if "profile" in data or "extras" in data:
        extras = cast("list[Any]", data.pop("extras", None) or [])
        core = legacy_to_core(
            str(data.pop("profile", "rv32i")),
            [str(e) for e in extras],
        )
        data = {"core": core, **data}
    return yaml.safe_dump(data, sort_keys=False)
