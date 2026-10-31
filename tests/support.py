"""Helpers shared by the test modules."""

import argparse
import shutil
import struct
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

GCC = "riscv32-unknown-elf-gcc"
OBJCOPY = "riscv32-unknown-elf-objcopy"
ISA = {"base": "i", "default_ext": "", "canonical_order": "MAFDQLCBJTPVNH"}

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
    root: Path, emit: str, only: str | None = None
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


_PHOFF, _PHENTSIZE, _SHENTSIZE = 52, 32, 40


def _elf_header(shoff: int, phnum: int) -> bytes:
    """Build the 52-byte header of a little-endian 32-bit RISC-V ELF."""
    header = bytearray(52)
    header[:4] = b"\x7fELF"
    header[4], header[5] = 1, 1
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


def write_rv32_header(root: Path, mailbox_addr: int) -> None:
    """Write include/rv32_test.h, with the mailbox at mailbox_addr."""
    include_dir = root / "include"
    include_dir.mkdir()
    (include_dir / "rv32_test.h").write_text(
        f"#define RV32_MAILBOX_ADDR ((volatile unsigned int *)"
        f"0x{mailbox_addr:08X})\n"
        "extern void rv32_wait_restart(void) __attribute__((noreturn));\n"
        "static inline void RV32_PASS(void) { *RV32_MAILBOX_ADDR = 1; "
        "rv32_wait_restart(); }\n"
        "static inline void RV32_FAIL(void) { *RV32_MAILBOX_ADDR = 2; "
        "rv32_wait_restart(); }\n"
    )
