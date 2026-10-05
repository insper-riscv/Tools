"""The SDRAM debug backend: the RAM target, the JTAG helpers, the sparse dump."""

from pathlib import Path
from typing import Any

import pytest

from riscv_tools import (
    mailbox,
    mem_validator,
    ram_dump,
    ram_target,
    ram_zero,
    sdram_debug,
)
from riscv_tools.jtag import JtagLink
from riscv_tools.ram_target import SdramDebugRam

LINK = JtagLink(hardware_name="cable", device_name="device")


class FakeTcl:
    """Stands for run_tcl: records the calls and answers a read from a Python dict."""

    def __init__(self, memory: dict[int, int] | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.memory = memory or {}

    def __call__(self, _link: JtagLink, script: str, *args: Any) -> Any:
        """Record the call and answer it like the script would."""
        self.calls.append((script, *args))
        stdout = ""
        if args[0] == "read":
            first, count = int(args[1]), int(args[2])
            stdout = "WORDS=" + " ".join(
                str(self.memory.get(first + i, 0)) for i in range(count)
            )
        return type("Completed", (), {"stdout": stdout})()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeTcl:
    tcl = FakeTcl({0x10: 7, 0x11: 8, 0x12: 9, 0x40: 1})
    monkeypatch.setattr(sdram_debug.core, "run_tcl", tcl)
    return tcl


def test_target_from_config() -> None:
    assert ram_target.target_from_config({"quartus": {"ram_mem_instance": 2}}) == 2
    cfg = {"quartus": {"ram_backend": "ismce", "ram_mem_instance": 3}}
    assert ram_target.target_from_config(cfg) == 3
    cfg = {"quartus": {"ram_backend": "sdram_debug", "ram_mem_instance": None}}
    assert ram_target.target_from_config(cfg) == SdramDebugRam()
    with pytest.raises(ValueError):
        ram_target.target_from_config({"quartus": {"ram_backend": "usb"}})


def test_reads_and_writes_go_to_the_debug_port(fake: FakeTcl) -> None:
    assert sdram_debug.read_words(LINK, 0x10, 3) == [7, 8, 9]
    sdram_debug.write_word(LINK, 0x20, 5)
    sdram_debug.write_word(LINK, 0x21, 6, 0b0101)
    sdram_debug.fill(LINK, 0x100, 64, 0)
    assert fake.calls == [
        ("sdram_dbg.tcl", "read", 0x10, 3),
        ("sdram_dbg.tcl", "write", 0x20, 5, 0xF),
        ("sdram_dbg.tcl", "write", 0x21, 6, 0b0101),
        ("sdram_dbg.tcl", "fill", 0x100, 64, 0),
    ]


def test_a_missing_reply_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = type("Completed", (), {"stdout": "oops"})()
    monkeypatch.setattr(sdram_debug.core, "run_tcl", lambda *_args, **_kw: reply)
    with pytest.raises(RuntimeError, match="no WORDS= line"):
        sdram_debug.read_words(LINK, 0)


def test_the_mailbox_and_the_go_flag_use_the_target(fake: FakeTcl) -> None:
    # byte address 0x40 above a RAM base of 0: word offset 0x10
    assert mailbox.read_mailbox(LINK, SdramDebugRam(), 0x40000000, 0x40000040) == 7
    mailbox.pulse_go_flag(LINK, SdramDebugRam(), 0x40000000, 0x40000080)
    assert fake.calls == [
        ("sdram_dbg.tcl", "read", 0x10, 1),
        ("sdram_dbg.tcl", "write", 0x20, 1, 0xF),
    ]


def test_the_mailbox_is_cleared_before_a_test(fake: FakeTcl) -> None:
    mailbox.clear_mailbox(LINK, SdramDebugRam(), 0x40000000, 0x40000040)
    assert fake.calls == [("sdram_dbg.tcl", "write", 0x10, 0, 0xF)]


def test_zero_ram_fills_the_sdram(fake: FakeTcl) -> None:
    ram_zero.zero_ram(LINK, SdramDebugRam(), 1 << 24)
    assert fake.calls == [("sdram_dbg.tcl", "fill", 0, 1 << 24, 0)]


@pytest.mark.usefixtures("fake")
def test_a_dump_of_the_sdram_needs_the_words(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="too big to dump whole"):
        ram_dump.dump_ram(LINK, SdramDebugRam(), tmp_path / "x.mif")


def test_a_sparse_dump_reads_runs_and_parses_back(
    fake: FakeTcl, tmp_path: Path
) -> None:
    out = tmp_path / "dump.mif"
    ram_dump.dump_ram(LINK, SdramDebugRam(), out, [0x12, 0x10, 0x11, 0x40, 0x10])
    # two runs: 0x10..0x12 and 0x40
    assert fake.calls == [
        ("sdram_dbg.tcl", "read", 0x10, 3),
        ("sdram_dbg.tcl", "read", 0x40, 1),
    ]
    assert mem_validator.parse_mif_words(out) == {0x10: 7, 0x11: 8, 0x12: 9, 0x40: 1}


def test_the_golden_names_the_words_to_dump(tmp_path: Path) -> None:
    golden = tmp_path / "golden.json"
    golden.write_text(
        '{"0x00000010": 1, "0x00000011": 2, "0x00000044": 3, "0x00000045": 4}'
    )
    assert mem_validator.golden_word_offsets(golden) == [4, 0x11]


def test_a_sparse_dump_compares_with_a_golden(fake: FakeTcl, tmp_path: Path) -> None:
    fake.memory = {4: 0x04030201}
    golden = tmp_path / "golden.json"
    golden.write_text(
        '{"0x00000010": 1, "0x00000011": 2, "0x00000012": 3, "0x00000013": 4}'
    )
    out = tmp_path / "dump.mif"
    ram_dump.dump_ram(
        LINK, SdramDebugRam(), out, mem_validator.golden_word_offsets(golden)
    )
    assert mem_validator.compare(out, golden)
    golden.write_text('{"0x00000010": 9}')
    assert not mem_validator.compare(out, golden)
