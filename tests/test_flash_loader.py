"""The FLASH loader: host side and the choice of the write method."""

from pathlib import Path
from typing import Any

import pytest
from support import check, check_equal

from riscv_tools import flash_loader, htif, rom_writer
from riscv_tools.flash_loader import core as loader_core
from riscv_tools.jtag import JtagLink
from riscv_tools.orchestrator import jtag_run
from riscv_tools.rom_writer import core as writer_core

LINK = JtagLink(hardware_name="cable", device_name="device")


class FakeTcl:
    """Stands for run_tcl: records calls, answers reads from a list."""

    def __init__(self) -> None:
        """Start with no calls and no image."""
        self.calls: list[tuple[Any, ...]] = []
        self.image: list[int] = []

    def __call__(self, _link: JtagLink, script: str, *args: Any) -> Any:
        """Record the call and answer it like the script would."""
        self.calls.append((script, *args))
        stdout = ""
        if args[0] == "load":
            self.image = [
                int(line, 16)
                for line in Path(args[2]).read_text(encoding="utf-8").split()
            ]
        if args[0] == "read":
            first, count = int(args[1]), int(args[2])
            stdout = "WORDS=" + " ".join(
                str(self.image[first + i]) for i in range(count)
            )
        return type("Completed", (), {"stdout": stdout})()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeTcl:
    """Replace run_tcl of the loader module."""
    tcl = FakeTcl()
    monkeypatch.setattr(loader_core, "run_tcl", tcl)
    return tcl


def write_mif(path: Path, words: dict[int, int], depth: int) -> Path:
    """Write a small .mif with the given words."""
    lines = [f"{a:X} : {v:08X};" for a, v in words.items()]
    path.write_text(
        encoding="utf-8",
        data=f"DEPTH = {depth};\nWIDTH = 32;\nADDRESS_RADIX = HEX;\n"
        "DATA_RADIX = HEX;\nCONTENT BEGIN\n" + "\n".join(lines) + "\nEND;\n",
    )
    return path


def test_checksum_adds_each_word_and_its_address() -> None:
    """The sum adds each word and its address, modulo 2**32."""
    check_equal(flash_loader.image_checksum(0, [1, 2, 3]), 1 + 3 + 5)
    check_equal(flash_loader.image_checksum(4, [1]), 5)
    check_equal(flash_loader.image_checksum(0, [0xFFFFFFFF, 1]), 1)


def test_load_image_passes_the_image_the_count_and_the_sum(
    fake: FakeTcl,
) -> None:
    """One session carries the file, the expected count and the sum."""
    flash_loader.load_image(LINK, [10, 20, 30], 2)
    (call,) = fake.calls
    check_equal(call[0], "flash_loader.tcl")
    check_equal(call[1], "load")
    check_equal(call[2], 2)
    check_equal(call[4:], (3, 10 + 2 + 20 + 3 + 30 + 4, "run"))
    check_equal(fake.image, [10, 20, 30])


def test_load_image_can_leave_the_core_halted(fake: FakeTcl) -> None:
    """Without a restart the script is told to hold the core."""
    flash_loader.load_image(LINK, [1], restart=False)
    check_equal(fake.calls[0][-1], "hold")


@pytest.mark.usefixtures("fake")
def test_read_words_parses_the_reply() -> None:
    """The words come back in address order."""
    flash_loader.load_image(LINK, [7, 8, 9])
    check_equal(flash_loader.read_words(LINK, 1, 2), [8, 9])


def test_read_words_without_a_reply_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A script that prints no WORDS line is an error."""

    def silent(_link: JtagLink, _script: str, *_args: Any) -> Any:
        """Answer with output that holds no WORDS line."""
        return type("Completed", (), {"stdout": "nothing"})()

    monkeypatch.setattr(loader_core, "run_tcl", silent)
    with pytest.raises(RuntimeError):
        flash_loader.read_words(LINK, 0, 1)


def test_halt_and_release_use_the_script(fake: FakeTcl) -> None:
    """Both commands are one call of the script."""
    flash_loader.halt(LINK)
    flash_loader.release(LINK)
    check_equal([c[1] for c in fake.calls], ["halt", "run"])


def test_mif_words_fills_the_gaps_with_zeros(tmp_path: Path) -> None:
    """The image runs from word 0 to the last word the file defines."""
    mif = write_mif(tmp_path / "a.mif", {0: 1, 3: 4}, 8)
    check_equal(rom_writer.mif_words(mif), [1, 0, 0, 4])


def test_method_from_config() -> None:
    """The key picks the method, with mem_edit as the default."""
    check_equal(rom_writer.method_from_config({"quartus": {}}), "mem_edit")
    cfg = {"quartus": {"rom_write_method": "jtag_loader"}}
    check_equal(rom_writer.method_from_config(cfg), "jtag_loader")
    with pytest.raises(ValueError, match="rom_write_method"):
        rom_writer.method_from_config({"quartus": {"rom_write_method": "x"}})


def test_write_rom_by_the_loader_restarts_the_core(
    fake: FakeTcl, tmp_path: Path
) -> None:
    """The loader method writes one copy and reports the restart."""
    mif = write_mif(tmp_path / "a.mif", {0: 5, 1: 6}, 4)
    check(rom_writer.write_rom(LINK, [0, 2], mif, "jtag_loader"))
    check_equal(fake.image, [5, 6])
    check(
        not rom_writer.write_rom(LINK, [0], mif, "jtag_loader", restart=False)
    )


def test_write_rom_by_the_editor_writes_every_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The editor method writes each instance and asks for the pulse."""
    seen: list[Any] = []

    def record(*args: Any) -> None:
        """Record the call."""
        seen.append(args)

    monkeypatch.setattr(writer_core.mem_edit, "write_full_multi", record)
    mif = write_mif(tmp_path / "a.mif", {0: 1}, 2)
    check(not rom_writer.write_rom(LINK, [0, 2], mif))
    check_equal(seen, [(LINK, [0, 2], mif)])


class Board:
    """Fakes the htif and rom_writer calls and keeps their order."""

    def __init__(self, restarts: bool) -> None:
        """Start with no events; restarts is what the write reports."""
        self.events: list[str] = []
        self.restarts = restarts

    def clear(self, *_args: Any) -> None:
        """Record the clearing of tohost."""
        self.events.append("clear")

    def pulse(self, *_args: Any) -> None:
        """Record the pulse of fromhost."""
        self.events.append("pulse")

    def passed(self, *_args: Any) -> int:
        """Answer that the test passed."""
        return htif.PASS

    def write(self, *_args: Any) -> bool:
        """Record the write and say whether the core restarted."""
        self.events.append("write")
        return self.restarts


def run_one_test(
    monkeypatch: pytest.MonkeyPatch, method: str, tmp_path: Path
) -> list[str]:
    """Run run_test_via_jtag with fakes and return what it did."""
    board = Board(method == "jtag_loader")
    monkeypatch.setattr(htif, "clear_tohost_configured", board.clear)
    monkeypatch.setattr(htif, "pulse_fromhost_configured", board.pulse)
    monkeypatch.setattr(htif, "read_tohost_configured", board.passed)
    monkeypatch.setattr(
        jtag_run.rom_writer, "write_rom_configured", board.write
    )
    cfg: dict[str, Any] = {
        "quartus": {"rom_write_method": method, "poll_interval_seconds": 0}
    }
    entry = {"mif": "a.mif", "timeout_s": 1}
    check_equal(
        jtag_run.run_test_via_jtag(cfg, LINK, entry, tmp_path), htif.PASS
    )
    return board.events


def test_the_pulse_follows_only_the_editor_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The loader restarts the core, so the host does not pulse."""
    check_equal(
        run_one_test(monkeypatch, "mem_edit", tmp_path),
        ["clear", "write", "pulse"],
    )
    check_equal(
        run_one_test(monkeypatch, "jtag_loader", tmp_path),
        ["clear", "write"],
    )
