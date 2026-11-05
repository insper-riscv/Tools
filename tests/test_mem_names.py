"""Finding the memory editor instances by name instead of by index."""

from pathlib import Path
from typing import Any

import pytest
from support import check, check_equal

from riscv_tools import mem_edit, quartus_program, ram_target
from riscv_tools.jtag import JtagLink
from riscv_tools.mem_edit import names as names_core

LINK = JtagLink(hardware_name="cable", device_name="device")

# The listing of a board whose ROM was cut to FLAS by the editor.
LISTING = (
    "MEM 0 65536 32 RW ROM/RAM FLAS\n"
    "MEM 1 4096 32 RW ROM/RAM FLAS\n"
    "MEM 2 8192 32 RW ROM/RAM RAM\n"
    "COUNT=3\n"
)
SPLIT = (
    "MEM 0 1024 32 RW ROM/RAM FLASH\nMEM 1 8192 32 RW ROM/RAM RAM\nCOUNT=2\n"
)


class FakeListing:
    """Stands for run_tcl: counts the calls and answers the listing."""

    def __init__(self, text: str) -> None:
        """Start with the text the script prints and no calls."""
        self.text = text
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, _link: JtagLink, script: str, *args: Any) -> Any:
        """Record the call and answer it like the script would."""
        self.calls.append((script, *args))
        return type("Completed", (), {"stdout": self.text})()


def serve(monkeypatch: pytest.MonkeyPatch, text: str) -> FakeListing:
    """Make the listing of the board come from the fake."""
    mem_edit.invalidate()
    fake = FakeListing(text)
    monkeypatch.setattr(names_core, "run_tcl", fake)
    return fake


@pytest.fixture(autouse=True)
def clean_listings() -> None:
    """Start and end every test without a kept listing."""
    mem_edit.invalidate()


def test_parse_listing_reads_every_field() -> None:
    """Parse listing reads every field."""
    found = names_core.parse_listing(LISTING)
    check_equal(
        found[2],
        mem_edit.MemInstance(index=2, depth=8192, width=32, name="RAM"),
    )
    check_equal([inst.name for inst in found], ["FLAS", "FLAS", "RAM"])


def test_parse_listing_accepts_an_unnamed_instance() -> None:
    """Parse listing accepts an unnamed instance."""
    found = names_core.parse_listing("MEM 0 16 8 W CONSTANT\nCOUNT=1\n")
    check_equal(found[0].name, "")


def test_parse_listing_rejects_a_cut_output() -> None:
    """Parse listing rejects a cut output."""
    with pytest.raises(RuntimeError):
        names_core.parse_listing("MEM 0 16 8 W CONSTANT\n")
    with pytest.raises(RuntimeError):
        names_core.parse_listing("MEM 0 16 8 W CONSTANT\nCOUNT=2\n")


def test_ram_resolves_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ram resolves by name."""
    serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"ram_mem_name": "RAM", "ram_mem_instance": 9}}
    check_equal(mem_edit.ram_instance(LINK, cfg), 1)


def test_rom_resolves_by_name_in_the_order_of_the_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rom resolves by name in the order of the names."""
    serve(
        monkeypatch,
        "MEM 0 8 32 RW ROM/RAM RAM\nMEM 1 8 32 RW ROM/RAM AAAA\n"
        "MEM 2 8 32 RW ROM/RAM BBB\nCOUNT=3\n",
    )
    cfg = {"quartus": {"rom_mem_names": ["BBB", "AAAA"]}}
    check_equal(mem_edit.rom_instances(LINK, cfg), [2, 1])


def test_name_cut_by_the_editor_matches_the_long_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Name cut by the editor matches the long names."""
    serve(monkeypatch, LISTING)
    cfg = {"quartus": {"rom_mem_names": ["FLASH", "FLASH_MEM"]}}
    check_equal(mem_edit.rom_instances(LINK, cfg), [0, 1])


def test_short_listed_name_is_not_a_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name listed whole matches only itself."""
    serve(monkeypatch, SPLIT)
    with pytest.raises(mem_edit.MemNameError):
        mem_edit.ram_instance(LINK, {"quartus": {"ram_mem_name": "RAMX"}})


def test_missing_name_lists_the_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing name lists the instances."""
    serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"rom_mem_names": ["FLASH", "BOOT"]}}
    with pytest.raises(mem_edit.MemNameError) as caught:
        mem_edit.rom_instances(LINK, cfg)
    message = str(caught.value)
    check("'BOOT'" in message)
    check("FLASH (index 0, 1024x32)" in message)
    check("RAM (index 1, 8192x32)" in message)


def test_missing_name_on_an_empty_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing name on an empty board says it has no instances."""
    serve(monkeypatch, "COUNT=0\n")
    with pytest.raises(mem_edit.MemNameError, match="no editable memory"):
        mem_edit.ram_instance(LINK, {"quartus": {"ram_mem_name": "RAM"}})


def test_ambiguous_ram_name_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguous ram name is refused."""
    serve(monkeypatch, LISTING)
    with pytest.raises(mem_edit.MemNameError, match="2 instances"):
        mem_edit.ram_instance(LINK, {"quartus": {"ram_mem_name": "FLASH"}})


def test_name_wins_over_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name wins over the index."""
    serve(monkeypatch, SPLIT)
    cfg = {
        "quartus": {
            "rom_mem_names": ["FLASH"],
            "rom_mem_instances": [5],
            "ram_mem_name": "RAM",
            "ram_mem_instance": 7,
        }
    }
    check_equal(mem_edit.rom_instances(LINK, cfg), [0])
    check_equal(mem_edit.ram_instance(LINK, cfg), 1)


def test_indices_still_work_without_asking_the_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indices still work without asking the board."""
    fake = serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"rom_mem_instances": [0, 3], "ram_mem_instance": 2}}
    check_equal(mem_edit.rom_instances(LINK, cfg), [0, 3])
    check_equal(mem_edit.ram_instance(LINK, cfg), 2)
    cfg: dict[str, Any] = {
        "quartus": {"rom_mem_names": [], "rom_mem_instances": [1]}
    }
    check_equal(mem_edit.rom_instances(LINK, cfg), [1])
    check_equal(fake.calls, [])


def test_the_board_is_listed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The board is listed once."""
    fake = serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"rom_mem_names": "FLASH", "ram_mem_name": "RAM"}}
    for _ in range(3):
        mem_edit.rom_instances(LINK, cfg)
        mem_edit.ram_instance(LINK, cfg)
    check_equal(fake.calls, [("list_mems.tcl",)])


def test_programming_the_board_drops_the_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Programming the board drops the listing."""
    fake = serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"ram_mem_name": "RAM"}}
    mem_edit.ram_instance(LINK, cfg)
    with pytest.raises(FileNotFoundError):
        quartus_program.program_only("cable", tmp_path, "none.sof")
    mem_edit.ram_instance(LINK, cfg)
    check_equal(len(fake.calls), 2)


def test_target_from_config_uses_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Target from config uses the name."""
    serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"ram_mem_name": "RAM", "ram_mem_instance": 1}}
    check_equal(ram_target.target_from_config(cfg, LINK), 1)
    with pytest.raises(ValueError, match="link"):
        ram_target.target_from_config(cfg)


def test_sdram_backend_never_asks_the_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sdram backend never asks the board."""
    fake = serve(monkeypatch, SPLIT)
    cfg = {"quartus": {"ram_backend": "sdram_debug", "ram_mem_name": "RAM"}}
    check_equal(
        ram_target.target_from_config(cfg, LINK), ram_target.SdramDebugRam()
    )
    check_equal(fake.calls, [])
