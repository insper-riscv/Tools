"""End-to-end test of generate_golden against real Spike and GCC.

Runs against the workstation's Spike and GCC toolchain; proves the whole
chain (compile -> run under Spike until tohost -> read the signature ->
emit golden JSON) actually works, for both a C test and a hand-written
asm test (see fixtures/htif_min/).

Skipped automatically if either tool isn't available, since neither
is guaranteed to be present in every environment this package's own
test suite runs in (see the top-level README).
"""

import json
import shutil
from pathlib import Path

import pytest
from support import link_bare

from riscv_tools.golden_generator import (
    generate_golden,
    symbol_range,
    write_golden_json,
)
from riscv_tools.spike_exec import SpikeTarget

GCC = "riscv32-unknown-elf-gcc"
NM = "riscv32-unknown-elf-nm"
ISA = "rv32im"

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "htif_min"
SPIKE_BIN = shutil.which("spike")

pytestmark = pytest.mark.skipif(
    shutil.which(GCC) is None or SPIKE_BIN is None,
    reason=f"needs {GCC} and spike on PATH (see insper-riscv/Infra)",
)

# Address/value the fixtures write, and the value each is expected to
# leave there; see pass_c.c / pass_asm.S.
ADDR = 0x80000100
EXPECTED = {
    "pass_c.c": 0xAABBCCDD,
    "pass_asm.S": 0x11223344,
}


def _compile(source: Path, tmp_path: Path) -> Path:
    elf = tmp_path / f"{source.stem}.elf"
    link_bare(
        [FIXTURES / "crt0.S", source],
        FIXTURES / "link.ld",
        elf,
        march=ISA,
        flags=["-Os", "-ffreestanding"],
    )
    return elf


def _target() -> SpikeTarget:
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    return SpikeTarget(
        spike_bin=SPIKE_BIN,
        nm_bin=NM,
        isa=ISA,
        mem_regions=[(0x80000000, 0x10000)],
        tohost_symbol="tohost",
    )


@pytest.mark.parametrize("source_name", ["pass_c.c", "pass_asm.S"])
def test_generate_golden_reads_back_expected_bytes(
    source_name: str, tmp_path: Path
) -> None:
    """Generate golden reads back expected bytes."""
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / source_name, tmp_path)

    golden = generate_golden(
        _target(),
        elf,
        (ADDR, ADDR + 4),
    )

    expected_word = EXPECTED[source_name]
    expected_bytes = {
        ADDR + i: (expected_word >> (8 * i)) & 0xFF for i in range(4)
    }
    assert golden == expected_bytes


def test_generate_golden_json_round_trips_through_compare(
    tmp_path: Path,
) -> None:
    """Exercise the full CLI-facing path.

    Same as above, but writes the golden JSON to disk, then reads it
    back with json.loads the way a human/CI would, confirming the
    file itself (not just the in-memory dict) is correct.
    """
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / "pass_c.c", tmp_path)

    golden = generate_golden(
        _target(),
        elf,
        (ADDR, ADDR + 4),
    )
    out_path = tmp_path / "golden.json"
    write_golden_json(golden, out_path)

    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text())
    assert {int(k, 16): v for k, v in on_disk.items()} == golden
    assert (
        on_disk[f"0x{ADDR:08X}"] == 0xDD
    )  # low byte of 0xAABBCCDD, little-endian


def test_symbol_range_resolves_address_and_size(tmp_path: Path) -> None:
    """symbol_range should resolve a global's address and byte size.

    pass_c_symbol.c declares `volatile unsigned int results[2]`, an
    8-byte object, with no explicit address, unlike the other
    fixtures' hardcoded 0x80000100 pointer. Proves --symbol needs no
    address arithmetic from the caller at all, just a name.
    """
    elf = _compile(FIXTURES / "pass_c_symbol.c", tmp_path)
    start, end = symbol_range(NM, elf, "results")
    assert end - start == 8  # 2 * sizeof(unsigned int)


def test_generate_golden_by_symbol_matches_explicit_start_end(
    tmp_path: Path,
) -> None:
    """generate_golden fed symbol_range should match a chosen range.

    Cross-checks the --symbol path against the pre-existing
    --start/--end path on the same fixture, rather than just trusting
    symbol_range's own address/size math in isolation.
    """
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / "pass_c_symbol.c", tmp_path)
    start, end = symbol_range(NM, elf, "results")

    golden = generate_golden(
        _target(),
        elf,
        (start, end),
    )

    expected_words = [0xAABBCCDD, 0x11223344]
    expected_bytes = {
        start + 4 * i + b: (word >> (8 * b)) & 0xFF
        for i, word in enumerate(expected_words)
        for b in range(4)
    }
    assert golden == expected_bytes


def test_generate_golden_rounds_a_partial_word_range_up(
    tmp_path: Path,
) -> None:
    """Generate golden rounds a partial word range up."""
    assert SPIKE_BIN is not None  # guaranteed by pytestmark's skipif above
    elf = _compile(FIXTURES / "pass_asm.S", tmp_path)

    golden = generate_golden(
        _target(),
        elf,
        (ADDR, ADDR + 1),
    )

    assert golden == {
        ADDR + i: (0x11223344 >> (8 * i)) & 0xFF for i in range(4)
    }
