"""End-to-end test of golden_generator.generate_golden against real Spike + GCC.

Runs against a real built Spike (vendor/riscv-isa-sim) and a real GCC
toolchain — proves the whole chain (compile -> run under Spike's
debug console -> wait for tohost -> read memory -> emit golden JSON)
actually works, for both a C test and a hand-written asm test (see
fixtures/htif_min/).

Skipped automatically if either tool isn't available, since neither
is guaranteed to be present in every environment this package's own
test suite runs in (vendor/riscv-isa-sim must be built first: cd
vendor/riscv-isa-sim && ./configure && make — needs
device-tree-compiler and libboost-dev; see the top-level README).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from riscv_tools.golden_generator import generate_golden, write_golden_json

GCC = "riscv32-unknown-elf-gcc"
NM = "riscv32-unknown-elf-nm"
ISA = "rv32im"

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "htif_min"
BUILT_SPIKE = REPO_ROOT / "vendor" / "riscv-isa-sim" / "build" / "spike"

SPIKE_BIN = shutil.which("spike") or (
    str(BUILT_SPIKE) if BUILT_SPIKE.exists() else None
)

pytestmark = pytest.mark.skipif(
    shutil.which(GCC) is None or SPIKE_BIN is None,
    reason=(
        f"needs {GCC} on PATH and a built spike binary (PATH or {BUILT_SPIKE}); "
        "see vendor/riscv-isa-sim's build instructions in the README"
    ),
)

# Address/value the fixtures write, and the value each is expected to
# leave there — see pass_c.c / pass_asm.S.
ADDR = 0x80000100
EXPECTED = {
    "pass_c.c": 0xAABBCCDD,
    "pass_asm.S": 0x11223344,
}


def _compile(source: Path, tmp_path: Path) -> Path:
    elf = tmp_path / f"{source.stem}.elf"
    subprocess.run(
        [
            GCC,
            f"-march={ISA}",
            "-mabi=ilp32",
            "-Os",
            "-ffreestanding",
            "-nostdlib",
            "-nostartfiles",
            f"-Wl,-T,{FIXTURES / 'link.ld'}",
            str(FIXTURES / "crt0.S"),
            str(source),
            "-o",
            str(elf),
        ],
        check=True,
    )
    return elf


@pytest.mark.parametrize("source_name", ["pass_c.c", "pass_asm.S"])
def test_generate_golden_reads_back_expected_bytes(
    source_name: str, tmp_path: Path
) -> None:
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / source_name, tmp_path)

    golden = generate_golden(
        spike_bin=SPIKE_BIN,
        nm_bin=NM,
        elf_path=elf,
        isa=ISA,
        tohost_symbol="tohost",
        addr_start=ADDR,
        addr_end=ADDR + 4,
    )

    expected_word = EXPECTED[source_name]
    expected_bytes = {ADDR + i: (expected_word >> (8 * i)) & 0xFF for i in range(4)}
    assert golden == expected_bytes


def test_generate_golden_json_round_trips_through_compare(tmp_path: Path) -> None:
    """Exercise the full CLI-facing path.

    Same as above, but writes the golden JSON to disk, then reads it
    back with json.loads the way a human/CI would, confirming the
    file itself (not just the in-memory dict) is correct.
    """
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / "pass_c.c", tmp_path)

    golden = generate_golden(
        spike_bin=SPIKE_BIN,
        nm_bin=NM,
        elf_path=elf,
        isa=ISA,
        tohost_symbol="tohost",
        addr_start=ADDR,
        addr_end=ADDR + 4,
    )
    out_path = tmp_path / "golden.json"
    write_golden_json(golden, out_path)

    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text())
    assert {int(k, 16): v for k, v in on_disk.items()} == golden
    assert on_disk[f"0x{ADDR:08X}"] == 0xDD  # low byte of 0xAABBCCDD, little-endian
