"""The board identification: the cases of the plan, by fixtures."""

from dataclasses import replace

import pytest
from board_support import host
from support import check_equal

from riscv_tools.board import (
    BoardBusyError,
    BoardError,
    InventoryEntry,
    Request,
    scan,
    select_board,
)
from riscv_tools.board.inventory import Inventory
from riscv_tools.board.register import register
from riscv_tools.jtag.hardware import parse_jtagconfig, same_idcode

DE0CV = InventoryEntry("de0-cv-ws", "de0-cv", "pci-0000:00:14.0-usb-0:2")
TWINS = (
    InventoryEntry("de0-cv-ws", "de0-cv", "pci-0000:00:14.0-usb-0:2"),
    InventoryEntry("de0-cv-ws-2", "de0-cv", "pci-0000:00:14.0-usb-0:4"),
)


def test_the_parser_reads_cables_chains_and_errors() -> None:
    """Every cable comes out with its devices or its error."""
    broken = parse_jtagconfig(
        "1) USB-Blaster [1-2]\n  Unable to read device chain - JTAG chain "
        "broken\n\n2) DE-SoC [USB-1]\n  4BA00477   SOCVHPS\n  02D020DD   X\n"
    )
    check_equal(
        [c.name for c in broken],
        ["USB-Blaster [1-2]", "DE-SoC [USB-1]"],
        "names",
    )
    check_equal(broken[0].broken, True, "broken")
    check_equal(broken[0].bus_port, "1-2", "bus port")
    check_equal(broken[1].bus_port, None, "blaster II has no bus port")
    check_equal(
        broken[1].devices[1].identity, "@2: X (0x02D020DD)", "identity"
    )
    check_equal(parse_jtagconfig(""), [], "empty")


def test_the_idcode_comparison_ignores_the_version() -> None:
    """The top 4 bits of an IDCODE are the version, not the identity."""
    check_equal(same_idcode("4BA00477", "0BA00477"), True, "version")
    check_equal(same_idcode("02B050DD", "031050DD"), False, "other device")


def test_case_1_one_cable_one_candidate() -> None:
    """A cable with one candidate is that board, with no inventory."""
    chosen = select_board(host("one-chain"), Request(platform_board="auto"))
    check_equal(chosen.board, "de0-cv", "board")
    check_equal(chosen.cable, "USB-Blaster [1-2]", "cable")
    check_equal(chosen.device, "@1: 5CE(BA4|FA4) (0x02B050DD)", "device")
    check_equal(chosen.id, "de0-cv-ws", "id")
    check_equal(
        str(chosen.lock_file), "/locks/de0cv-ws.lock", "legacy lock name"
    )


def test_the_four_cables_of_the_workstation_pick_by_idcode() -> None:
    """Each board is found among four cables, whatever the order."""
    env = host("four-cables")
    for board, cable in (
        ("de0-cv", "[1-2]"),
        ("de2-115", "[1-3]"),
        ("de10-lite", "[1-6]"),
    ):
        chosen = select_board(env, Request(board=board))
        check_equal(chosen.cable, f"USB-Blaster {cable}", board)
    check_equal(len(env.reports()), 4, "four cables")


def test_case_2_two_equal_boards_need_the_inventory() -> None:
    """Two DE0-CV: --board alone is an error that lists both cables."""
    env = host("two-same")
    with pytest.raises(BoardError, match="2 boards match") as raised:
        select_board(env, Request(board="de0-cv"))
    check_equal(raised.value.case, 2, "case")
    check_equal(
        "[1-2]" in str(raised.value) and "[1-4]" in str(raised.value),
        True,
        "lists",
    )


def test_case_2_the_inventory_tells_them_apart() -> None:
    """With the ports registered, --board-id picks one, by its port."""
    env = host("two-same", TWINS)
    chosen = select_board(env, Request(board_id="de0-cv-ws-2"))
    check_equal(chosen.cable, "USB-Blaster [1-4]", "cable of the second")
    check_equal(str(chosen.lock_file), "/locks/de0-cv-ws-2.lock", "own lock")
    first = select_board(env, Request(board_id="de0-cv-ws"))
    check_equal(first.cable, "USB-Blaster [1-2]", "cable of the first")


def test_the_free_flag_takes_the_first_free_board() -> None:
    """--free skips the busy board of two equal ones, in port order."""
    env = host("two-same", TWINS, busy=frozenset({"de0-cv-ws.lock"}))
    chosen = select_board(env, Request(board="de0-cv", free=True))
    check_equal(chosen.id, "de0-cv-ws-2", "the free one")
    both = host(
        "two-same",
        TWINS,
        busy=frozenset({"de0-cv-ws.lock", "de0-cv-ws-2.lock"}),
    )
    with pytest.raises(BoardBusyError):
        select_board(both, Request(board="de0-cv", free=True))


def test_case_3_each_host_has_its_own_inventory() -> None:
    """The id carries the host, and so does the lock file."""
    env = host("one-chain")
    ws = select_board(env, Request(board="de0-cv"))
    check_equal(ws.id, "de0-cv-ws", "id")
    other = Inventory("laptop", env.inventory.lock_dir)
    check_equal(
        str(other.lock_path("de0-cv", None)),
        "/locks/de0cv-laptop.lock",
        "laptop lock",
    )


def test_case_4_same_idcode_several_devices_warns_variant() -> None:
    """020F70DD is three devices; the board declares which one."""
    chosen = select_board(
        host("same-idcode-two-boards"), Request(board="de2-115")
    )
    check_equal(len(chosen.warnings), 1, "warning")
    check_equal(
        "does not prove the variant" in chosen.warnings[0], True, "text"
    )


def test_case_5_same_device_other_board_needs_board_or_inventory() -> None:
    """The EP4CE22 cable may be two boards; --board decides."""
    env = host("four-cables", extra_boards=True)
    reports = {r.cable.name: r for r in env.reports()}
    check_equal(
        reports["USB-Blaster [1-5]"].candidates,
        ("de0-nano", "other-ep4ce22"),
        "two candidates",
    )
    with pytest.raises(BoardError, match="2 boards match"):
        select_board(
            env,
            Request(
                platform_board="auto", allowed=("de0-nano", "other-ep4ce22")
            ),
        )
    chosen = select_board(env, Request(board="de0-nano"))
    check_equal(chosen.cable, "USB-Blaster [1-5]", "cable")
    inv = (InventoryEntry("nano-ws", "de0-nano", "pci-0000:00:14.0-usb-0:5"),)
    by_inventory = host("four-cables", inv, extra_boards=True)
    check_equal(
        select_board(by_inventory, Request(allowed=("de0-nano",))).id,
        "nano-ws",
        "inventory",
    )


def test_case_6_the_10m50_variants_are_not_told_apart() -> None:
    """031050DD gives DA or DC; the warning names both."""
    chosen = select_board(host("four-cables"), Request(board="de10-lite"))
    check_equal("10M50DA(.|ES)/10M50DC" in chosen.warnings[0], True, "warning")


def test_case_7_unknown_idcode_lists_what_was_searched() -> None:
    """A cable no board owns is an error with the IDCODEs searched."""
    with pytest.raises(BoardError, match="IDCODE 12345678") as raised:
        select_board(host("unknown"), Request(platform_board="auto"))
    check_equal(raised.value.case, 7, "case")
    with pytest.raises(BoardError, match="no board found") as empty:
        select_board(host("empty"), Request(board="de0-cv"))
    check_equal(empty.value.case, 7, "no cable at all")
    check_equal("02B050DD" in str(empty.value), True, "searched IDCODE")


def test_case_8_a_broken_chain_is_an_infrastructure_error() -> None:
    """The broken cable is reported, the healthy one selectable."""
    env = host("broken")
    with pytest.raises(BoardError, match="chain of USB-Blaster") as raised:
        select_board(env, Request(board="de0-cv"))
    check_equal(raised.value.case, 8, "case")
    check_equal(
        select_board(env, Request(board="de2-115")).cable,
        "USB-Blaster [1-3]",
        "ok",
    )
    with pytest.raises(BoardError) as forced:
        select_board(env, Request(cable="USB-Blaster [1-2]"))
    check_equal(forced.value.case, 8, "forced cable")


def test_case_9_a_busy_board_is_refused_by_auto() -> None:
    """Auto takes free boards; all busy raises with the owners."""
    busy = frozenset({"de0cv-ws.lock"})
    with pytest.raises(BoardBusyError, match="busy"):
        select_board(
            host("one-chain", busy=busy), Request(platform_board="auto")
        )
    named = select_board(host("one-chain", busy=busy), Request(board="de0-cv"))
    check_equal(named.free, False, "named board reports it is busy")


def test_the_precedence_cable_id_board_platform() -> None:
    """--cable beats --board-id, then --board, then board:."""
    env = host("four-cables", (DE0CV,))
    by_platform = select_board(env, Request(platform_board="de2-115"))
    check_equal(by_platform.board, "de2-115", "platform")
    by_board = select_board(
        env, Request(board="de10-lite", platform_board="de2-115")
    )
    check_equal(by_board.board, "de10-lite", "board over platform")
    by_id = select_board(env, Request(board_id="de0-cv-ws", board="de10-lite"))
    check_equal(by_id.board, "de0-cv", "id over board")
    by_cable = select_board(
        env, Request(cable="USB-Blaster [1-3]", board_id="de0-cv-ws")
    )
    check_equal(by_cable.cable, "USB-Blaster [1-3]", "cable over id")
    check_equal(
        by_cable.board,
        "de2-115",
        "cable decides the board when nothing else is expected",
    )


def test_a_forced_cable_still_checks_the_idcode() -> None:
    """--cable with a board whose IDCODE the cable lacks is refused."""
    env = host("four-cables")
    with pytest.raises(BoardError, match="expects IDCODE 02B050DD"):
        select_board(env, Request(cable="USB-Blaster [1-3]", board="de0-cv"))
    with pytest.raises(BoardError, match="not found"):
        select_board(env, Request(cable="USB-Blaster [9-9]"))


def test_an_unknown_id_or_board_lists_the_known_ones() -> None:
    """A name that does not exist is answered with the known ones."""
    env = host("one-chain", (DE0CV,))
    with pytest.raises(BoardError, match="known ids: de0-cv-ws"):
        select_board(env, Request(board_id="nope"))
    with pytest.raises(BoardError, match="known boards: de0-cv"):
        select_board(env, Request(board="nope"))


def test_a_moved_board_fails_with_the_idcode_message() -> None:
    """The port of an entry now answers another IDCODE (rule V17)."""
    moved = (
        InventoryEntry("de0-cv-ws", "de0-cv", "pci-0000:00:14.0-usb-0:3"),
    )
    env = host("four-cables", moved)
    with pytest.raises(BoardError, match="IDCODE mismatch"):
        select_board(env, Request(board_id="de0-cv-ws"))
    absent = (
        InventoryEntry("de0-cv-ws", "de0-cv", "pci-0000:00:14.0-usb-0:7"),
    )
    with pytest.raises(BoardError, match="no cable at"):
        select_board(
            host("four-cables", absent), Request(board_id="de0-cv-ws")
        )


def test_the_scan_is_ordered_by_port_not_by_listing() -> None:
    """Reversing the listing does not change the order of reports."""
    env = host("four-cables")
    reversed_env = replace(env, cables=env.cables[::-1])
    check_equal(
        [r.port for r in reversed_env.reports()],
        [r.port for r in env.reports()],
        "port order",
    )


def test_register_saves_the_certain_cables_and_numbers_twins() -> None:
    """Certain cables get an id, twins a number, ambiguous ones wait."""
    env = host("two-same")
    saved, notes = register(env.inventory, env.reports(), {})
    check_equal(
        [e.id for e in saved.entries], ["de0-cv-ws", "de0-cv-ws-2"], "ids"
    )
    check_equal(notes, [], "no notes")
    ambiguous = host("four-cables", extra_boards=True)
    _, waiting = register(ambiguous.inventory, ambiguous.reports(), {})
    check_equal(len(waiting), 1, "the EP4CE22 cable waits")
    port = "pci-0000:00:14.0-usb-0:5"
    assigned, none = register(
        ambiguous.inventory, ambiguous.reports(), {port: "de0-nano"}
    )
    check_equal(none, [], "assigned")
    check_equal(len(assigned.entries), 4, "all four saved")


def test_the_scan_reports_candidates_and_problems() -> None:
    """The unknown cable has a problem, the known one a board."""
    env = host("unknown")
    report = scan(env.cables, env.boards, env.inventory, env.resolve_port)[0]
    check_equal(report.candidates, (), "no candidate")
    check_equal(report.problem is not None, True, "problem")
