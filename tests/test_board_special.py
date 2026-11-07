"""DE10-Nano and MKR Vidor 4000, by fixtures only."""

import yaml
from board_support import FIXTURES, host
from multifpga_support import BOARDS
from support import check_equal

from riscv_tools.board import Request, select_board
from riscv_tools.board.doctor import FAIL, OK, WARN, Check, run_doctor
from riscv_tools.board.usb import parse_lsusb
from riscv_tools.board.usb_only import usb_only
from riscv_tools.jtag.hardware import parse_jtagconfig

BLASTER_II_COLD = "Bus 001 Device 007: ID 09fb:6010 Altera DE-SoC\n"
BLASTER_II_WARM = "Bus 001 Device 007: ID 09fb:6810 Altera DE-SoC\n"
VIDOR = "Bus 001 Device 004: ID 2341:8056 Arduino SA Arduino MKR Vidor 4000\n"


def _levels(checks: list[Check]) -> dict[str, str]:
    """Map each check name to its level."""
    return {c.name: c.level for c in checks}


def test_the_de10_nano_is_found_by_its_two_idcodes_and_cable() -> None:
    """DE-SoC with HPS DAP and FPGA: the FPGA is the second device."""
    chosen = select_board(host("de10-nano"), Request(platform_board="auto"))
    check_equal(chosen.board, "de10-nano", "board")
    check_equal(chosen.cable, "DE-SoC [USB-1]", "cable")
    check_equal(
        chosen.device, "@2: 5CSE(BA6|MA6)/.. (0x02D020DD)", "FPGA device"
    )
    check_equal(chosen.idcode, "02D020DD", "FPGA idcode")
    check_equal(chosen.port, None, "a blaster II name has no bus-port")


def test_a_plain_blaster_is_not_the_de10_nano() -> None:
    """The FPGA IDCODE on a plain USB-Blaster is not a DE10-Nano."""
    text = "1) USB-Blaster [1-2]\n  02D020DD   5CSE(BA6|MA6)/..\n"
    env = host("one-chain")
    cables = parse_jtagconfig(text)
    env = type(env)(
        env.boards, env.inventory, cables, env.resolve_port, env.lock_free
    )
    check_equal([r.candidates for r in env.reports()], [()], "no candidate")


def test_the_de10_nano_doctor_suggests_the_hps_setup() -> None:
    """Error 209025 is prevented by advice, nothing is changed."""
    checks = run_doctor(host("de10-nano"), [], [])
    check_equal(
        _levels(checks)["HPS in the chain of DE-SoC [USB-1]"], WARN, "hps"
    )


def test_the_doctor_tells_when_the_blaster_ii_firmware_is_not_loaded() -> None:
    """09fb:6010 means jtagd has not loaded the firmware yet."""
    usb = parse_lsusb(BLASTER_II_COLD)
    checks = run_doctor(host("empty"), usb, [])
    check_equal(_levels(checks)["USB-Blaster II"], WARN, "cold")
    warm = run_doctor(host("empty"), parse_lsusb(BLASTER_II_WARM), [])
    check_equal(_levels(warm)["DE10-Nano cable"], WARN, "warm without a cable")
    present = run_doctor(host("de10-nano"), parse_lsusb(BLASTER_II_WARM), [])
    check_equal("DE10-Nano cable" in _levels(present), False, "cable seen")


def test_the_vidor_only_gets_instructions() -> None:
    """The MKR Vidor on the USB with no cable gets instructions."""
    checks = run_doctor(host("empty"), parse_lsusb(VIDOR), [])
    vidor = next(c for c in checks if c.name == "MKR Vidor 4000")
    check_equal(vidor.level, WARN, "level")
    check_equal("USBBlaster sketch" in vidor.hint, True, "tells the sketch")
    check_equal("do not write it" in vidor.hint, True, "does not write it")


def test_the_vidor_with_the_sketch_is_a_usb_blaster() -> None:
    """With the sketch the emulated blaster is found."""
    text = "1) USB-Blaster [1-4]\n  020F20DD   10CL016\n"
    base = host("empty")
    env = type(base)(
        base.boards,
        base.inventory,
        parse_jtagconfig(text),
        base.resolve_port,
        base.lock_free,
    )
    check_equal(
        select_board(env, Request(board="mkr-vidor-4000")).board,
        "mkr-vidor-4000",
        "found",
    )
    checks = run_doctor(env, parse_lsusb(VIDOR), [])
    check_equal(
        "MKR Vidor 4000" in _levels(checks), False, "no instruction needed"
    )


def test_the_doctor_on_the_workstation_fixtures() -> None:
    """Four healthy cables: no failure, and the lsusb fixture parses."""
    usb = parse_lsusb((FIXTURES / "lsusb-workstation.txt").read_text())
    check_equal(len(usb), 9, "usb devices")
    checks = run_doctor(host("four-cables"), usb, [])
    check_equal(any(c.level == FAIL for c in checks), False, "no failure")
    check_equal(_levels(checks)["jtagconfig"], OK, "jtagconfig")
    check_equal(
        "MKR Vidor 4000" in _levels(checks),
        True,
        "the Vidor is on the workstation",
    )


def test_the_doctor_flags_a_broken_chain_and_stray_processes() -> None:
    """A broken chain fails with a hint; a stray process warns."""
    checks = run_doctor(host("broken"), [], [(4242, "quartus_pgm -c x")])
    levels = _levels(checks)
    check_equal(levels["chain of USB-Blaster [1-2]"], FAIL, "broken")
    check_equal(levels["process 4242"], WARN, "process")
    none = run_doctor(host("empty"), [], [])
    check_equal(_levels(none)["cables"], FAIL, "no cable")


def test_the_vidor_on_the_usb_is_listed_without_a_chain() -> None:
    """The SAMD21 in CDC state is the board, with no chain to read."""
    env = host("empty")
    found = usb_only(env.boards, parse_lsusb(VIDOR), env.reports())
    check_equal(
        [(o.board, o.usb_id) for o in found],
        [("mkr-vidor-4000", "2341:8056")],
        "vidor",
    )


def test_a_board_a_cable_explains_is_not_listed_as_usb_only() -> None:
    """The warm blaster II with its chain is no orphan."""
    env = host("de10-nano")
    found = usb_only(env.boards, parse_lsusb(BLASTER_II_WARM), env.reports())
    check_equal(found, [], "explained")


def test_the_cold_blaster_ii_is_listed_for_both_soc_boards() -> None:
    """Before the firmware loads the id fits both DE-SoC boards."""
    env = host("empty")
    found = usb_only(env.boards, parse_lsusb(BLASTER_II_COLD), env.reports())
    check_equal(
        [o.board for o in found], ["de0-nano-soc", "de10-nano"], "boards"
    )


def test_a_plain_usb_blaster_names_no_board() -> None:
    """09fb:6001 is every USB-Blaster, so it never marks a board."""
    env = host("empty")
    line = "Bus 001 Device 003: ID 09fb:6001 Altera Blaster\n"
    check_equal(
        usb_only(env.boards, parse_lsusb(line), env.reports()), [], "plain"
    )


def test_the_de0_nano_soc_is_told_from_the_de10_nano_by_the_fpga_idcode() -> (
    None
):
    """Same cable and HPS, different FPGA IDCODE."""
    chosen = select_board(host("de0-nano-soc"), Request(platform_board="auto"))
    check_equal(chosen.board, "de0-nano-soc", "board")
    check_equal(chosen.idcode, "02D010DD", "idcode")
    check_equal(chosen.device, "@2: 5CSE(BA4|MA4)/.. (0x02D010DD)", "device")


def test_the_vidor_pins_have_no_duplicate_ball() -> None:
    """The schematic resolved the seven balls of the official .qsf."""
    raw = yaml.safe_load((BOARDS / "mkr-vidor-4000" / "pins.yaml").read_text())
    balls = [s["pin"] for s in raw["signals"]]
    check_equal(len(balls), len(set(balls)), "unique balls")
    check_equal(raw["conflicts"], [], "conflicts")
    by_ball = {s["pin"]: s["name"] for s in raw["signals"]}
    check_equal(by_ball["L4"], "bHDMI_SDA", "L4")
    check_equal(by_ball["R7"], "oFLASH_HOLD", "R7")
    check_equal(by_ball["T7"], "oFLASH_WP", "T7")


def test_the_vidor_chain_idcode_is_the_one_of_the_quartus_database() -> None:
    """020F20DD is the 10CL016 (and EP3C16), not 020F10DD."""
    board = host("empty").boards["mkr-vidor-4000"]
    check_equal(board.jtag.chain[0].idcode, "020F20DD", "idcode")
