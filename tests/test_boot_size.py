"""Tests for the measure of the boot memory against the BOOT_MEMORY."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from support import (
    GCC,
    MAP_REGIONS,
    MAP_RESERVED,
    check_equal,
    check_in,
    check_not_in,
    dump_platform,
)

from riscv_tools.boot_size import (
    BootSize,
    boot_size_message,
    measure_boot_size,
)
from riscv_tools.boot_size.core import measure_script
from riscv_tools.cli import main
from riscv_tools.memory_map import render_all

OBJDUMP = "riscv32-unknown-elf-objdump"
# O que `wait_restart` reserva no começo da imagem da BOOT de teste.
RESERVED = 0x100
PLATFORM: dict[str, Any] = {
    "profile": "rv32i_zicsr",
    "boot": {"entry": "0x800", "wait_restart": "0x100"},
    "reserved": MAP_RESERVED,
    "regions": MAP_REGIONS,
    "generate": {"boot_ld": {"path": "out/boot_memory.ld"}},
}
BOOT = """\
    .section .text.reset
    .global _reset
_reset:
    j    start
    .section .text.wait_restart
start:
    li   t0, 1
#include "fragment.inc"
"""
needs_toolchain = pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which(OBJDUMP) is None,
    reason=f"needs {GCC} and {OBJDUMP} on PATH",
)


def _project(root: Path, nops: int, **changes: Any) -> Path:
    """Write a platform, its linker script and a boot memory of a size.

    Parameters
    ----------
    root : Path
        The project root.
    nops : int
        The `nop` instructions that the included fragment holds.
    **changes
        Top-level sections of the platform to replace.

    Returns
    -------
    Path
        The platform file.
    """
    platform = root / "platform.yaml"
    platform.write_text(dump_platform({**PLATFORM, **changes}))
    for path, text in render_all(platform, root).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    out = root / "out"
    out.mkdir(exist_ok=True)
    (out / "boot_memory.S").write_text(BOOT)
    (out / "fragment.inc").write_text(
        f"    .rept {nops}\n    nop\n    .endr\n"
    )
    return platform


def _measure(root: Path, platform: Path) -> BootSize:
    """Measure the project with the build under the root."""
    return measure_boot_size(platform, root, root / "build")


def test_the_measure_script_drops_only_the_end_assert() -> None:
    """The `ASSERT` against the memory goes, and the memory grows."""
    text = (
        "MEMORY { m (rx) : ORIGIN = 0x0, LENGTH = 0x1000 }\n"
        'ASSERT(SIZEOF(.a) <= 4,\n  "a grew")\n'
        'ASSERT(. <= ORIGIN(m) + LENGTH(m),\n  "exceeds")\n'
    )
    out = measure_script(text)
    check_in("a grew", out)
    check_not_in("exceeds", out)
    check_in("LENGTH = 0x10000000", out)


@needs_toolchain
def test_a_boot_memory_that_fits_is_measured(tmp_path: Path) -> None:
    """The size is where the image ends, gap included."""
    size = _measure(tmp_path, _project(tmp_path, 16))
    check_equal(size.limit, 2048)
    check_equal(size.base, "rv32i")
    check_equal(size.used, RESERVED + 4 + 64)
    check_equal(size.fits, True)
    check_in(
        "boot size OK: 324 of 2048 bytes (rv32i)", boot_size_message(size)
    )


@needs_toolchain
def test_the_bytes_are_counted_by_source_file(tmp_path: Path) -> None:
    """Instructions are attributed to the file that wrote them."""
    size = _measure(tmp_path, _project(tmp_path, 16))
    check_equal(size.by_file, {"out/fragment.inc": 64, "out/boot_memory.S": 8})


@needs_toolchain
def test_a_boot_memory_that_is_too_big_is_reported(tmp_path: Path) -> None:
    """The overflow is measured instead of refused by the linker."""
    size = _measure(tmp_path, _project(tmp_path, 800))
    check_equal(size.used, RESERVED + 4 + 3200)
    check_equal(size.fits, False)
    text = boot_size_message(size)
    check_in("V-B3 the boot memory of platform.yaml assembles to 3460", text)
    check_in("the BOOT_MEMORY has 2048, 1412 bytes over", text)
    check_in("out/fragment.inc", text)


@needs_toolchain
def test_a_base_e_core_is_built_for_rv32e(tmp_path: Path) -> None:
    """The base of the core is the `-march` of the build."""
    platform = _project(tmp_path, 2, profile="rv32e")
    check_equal(_measure(tmp_path, platform).base, "rv32e")


def test_a_platform_without_a_boot_linker_script_is_refused(
    tmp_path: Path,
) -> None:
    """There is no boot memory to measure."""
    platform = _project(tmp_path, 2, generate={})
    with pytest.raises(ValueError, match=r"no generate\.boot_ld"):
        measure_boot_size(platform, tmp_path, tmp_path / "build")


@needs_toolchain
def test_the_subcommand_exits_one_when_the_boot_is_too_big(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`check-boot-size` fails with V-B3 and passes when it fits."""
    argv = ["riscv-tools", "--root", str(tmp_path)]
    _project(tmp_path, 800)
    monkeypatch.setattr(
        "sys.argv", [*argv, "check-boot-size", "--platform", "platform.yaml"]
    )
    with pytest.raises(SystemExit) as caught:
        main()
    check_equal(caught.value.code, 1)
    check_in("V-B3", capsys.readouterr().err)
    _project(tmp_path, 16)
    main()
    check_in("boot size OK", capsys.readouterr().out)


def test_the_subcommand_exits_two_without_a_toolchain(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing compiler is a failure of the tool, not of the boot."""
    _project(tmp_path, 16)
    monkeypatch.setattr(
        "sys.argv",
        [
            "riscv-tools",
            "--root",
            str(tmp_path),
            "check-boot-size",
            "--platform",
            "platform.yaml",
            "--gcc",
            "no-such-gcc",
        ],
    )
    with pytest.raises(SystemExit) as caught:
        main()
    check_equal(caught.value.code, 2)
    check_in("no-such-gcc", capsys.readouterr().err)
