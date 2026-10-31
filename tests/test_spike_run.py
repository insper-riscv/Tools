"""Tests for spike_run."""

import shutil
from pathlib import Path

import pytest
from support import link_bare

from riscv_tools.spike_exec import SpikeTarget
from riscv_tools.spike_run import SpikeRunResult, run_elf

GCC = "riscv32-unknown-elf-gcc"
NM = "riscv32-unknown-elf-nm"
OBJCOPY = "riscv32-unknown-elf-objcopy"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "htif_min"
REGIONS = [(0x80000000, 0x10000)]

pytestmark = pytest.mark.skipif(
    shutil.which(GCC) is None or shutil.which("spike") is None,
    reason=f"needs {GCC} and spike on PATH (see insper-riscv/Infra)",
)


def _build(tmp_path: Path, crt0: Path, name: str) -> Path:
    elf = tmp_path / f"{name}.elf"
    link_bare([crt0, FIXTURES / "pass_asm.S"], FIXTURES / "link.ld", elf)
    return elf


def _run(elf: Path, timeout_s: float = 20.0) -> SpikeRunResult:
    target = SpikeTarget(
        spike_bin="spike",
        nm_bin=NM,
        objcopy_bin=OBJCOPY,
        isa="rv32im",
        mem_regions=REGIONS,
        tohost_symbol="tohost",
    )
    return run_elf(target, elf, timeout_s=timeout_s)


def test_run_elf_reports_pass_when_tohost_is_1(tmp_path: Path) -> None:
    """Run elf reports pass when tohost is 1."""
    result = _run(_build(tmp_path, FIXTURES / "crt0.S", "pass"))

    assert result.passed
    assert result.exit_code == 0


def test_run_elf_reports_fail_when_tohost_is_3(tmp_path: Path) -> None:
    """Run elf reports fail when tohost is 3."""
    crt0 = tmp_path / "crt0_fail.S"
    crt0.write_text(
        (FIXTURES / "crt0.S").read_text().replace("li   t0, 1", "li   t0, 3")
    )

    result = _run(_build(tmp_path, crt0, "fail"))

    assert not result.passed
    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_run_elf_times_out_when_tohost_is_never_written(
    tmp_path: Path,
) -> None:
    """Run elf times out when tohost is never written."""
    crt0 = tmp_path / "crt0_hang.S"
    crt0.write_text(
        (FIXTURES / "crt0.S").read_text().replace("sw   t0, 0(t1)", "nop")
    )

    result = _run(_build(tmp_path, crt0, "hang"), timeout_s=1.0)

    assert not result.passed
    assert result.exit_code is None
    assert "timed out" in result.output
