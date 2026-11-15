"""Tests of the MAX 10 ADC shell, the vendor IP and the pin roles."""

from pathlib import Path

import yaml
from peripherals_support import request
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_check import check_platform
from riscv_tools.board_generate import Generated, GenerateRequest, generate
from riscv_tools.board_generate.vendor_ip import vendor_ip
from riscv_tools.memory_map.platform_format import normalize

PLATFORM = {
    "peripherals": [{"name": "A", "kind": "adc", "chip": "max10", "base": 0}]
}
SOURCES = (
    "../../Peripherals/src/ADC/soc/max10_adc.vhd",
    "../../Peripherals/src/ADC/max10/max10_adc_ip.vhd",
)


def _edit(path: Path, old: str, new: str) -> None:
    """Replace a text in a file of the example."""
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )


def _text(result: Generated, suffix: str) -> str:
    """Join the lines of the generated file with the suffix."""
    name = next(n for n in result.files if n.endswith(suffix))
    return " ".join(result.files[name].split())


def _with_sources(req: GenerateRequest) -> GenerateRequest:
    """Give the request the sources that hold the ADC instance."""
    return GenerateRequest(
        req.platform_file,
        req.board,
        req.boards_dir,
        req.chips_dir,
        SOURCES,
        req.accept_inferred,
    )


def test_the_ip_is_recognised_by_the_file_that_instances_it() -> None:
    """The `.qip` line and the script point at the generator."""
    found = vendor_ip(SOURCES, PLATFORM)
    check_equal(
        found.qsf_lines,
        (
            "set_global_assignment -name QIP_FILE "
            "max10_adc_core/synthesis/max10_adc_core.qip",
        ),
    )
    script = found.files["generate_ip.sh"]
    check_in('"$here/../../Peripherals/src/ADC/max10/ip/generate.sh"', script)


def test_no_ip_without_the_instance() -> None:
    """Sources without the file add nothing to the project."""
    found = vendor_ip(("a.vhd", "b.v"), PLATFORM)
    check_equal(vendor_ip(SOURCES, {}).qsf_lines, ())
    check_equal(found.qsf_lines, ())
    check_equal(found.files, {})


def test_the_project_carries_the_ip(tmp_path: Path) -> None:
    """The `.qsf` includes the `.qip` and the script is written."""
    result = generate(_with_sources(request(tmp_path, "adc")))
    qsf = _text(result, ".qsf")
    check_in("QIP_FILE max10_adc_core/synthesis/max10_adc_core.qip", qsf)
    check_in("generate_ip.sh", " ".join(result.files))
    check_in("ADC_CLK_10", qsf)


def test_a_project_without_the_adc_has_no_ip(tmp_path: Path) -> None:
    """The other platforms get neither the line nor the script."""
    result = generate(_with_sources(request(tmp_path, "ir")))
    check_not_in("generate_ip.sh", " ".join(result.files))
    check_not_in("QIP_FILE max10", _text(result, ".qsf"))


def test_the_sdc_has_the_10_mhz_clock(tmp_path: Path) -> None:
    """ADC_CLK_10 is a 100 ns clock, asynchronous to the SoC."""
    sdc = _text(generate(request(tmp_path, "adc")), ".sdc")
    check_in("create_clock -name ADC_CLK_10 -period 100.000", sdc)
    check_in(
        "set_clock_groups -asynchronous -group [get_clocks {ADC_CLK_10", sdc
    )


def test_the_usb_dma_pins_are_optional(tmp_path: Path) -> None:
    """Without `dreq` and `dack` the entity ties them off."""
    text = _text(generate(request(tmp_path, "usb")), "_top.vhd")
    check_in("i_otg_dreq => '0'", text)
    check_in("o_otg_dack => open", text)


def test_the_usb_dma_pins_are_wired_when_the_board_has_them(
    tmp_path: Path,
) -> None:
    """A role that names `dreq` and `dack` reaches the entity."""
    req = request(tmp_path, "usb")
    board = req.boards_dir / "example" / "board.yaml"
    both = "int: OTG_INT, dreq: OTG_DREQ, dack: OTG_DACK}"
    _edit(board, "int: OTG_INT}", both)
    text = _text(generate(req), "_top.vhd")
    check_in("i_otg_dreq => OTG_DREQ", text)
    check_in("o_otg_dack => OTG_DACK", text)


def test_two_peripherals_on_one_pin_are_an_error(tmp_path: Path) -> None:
    """The I2C pair shared by the EEPROM and the ADXL345 is V25."""
    req = request(tmp_path, "adxl345")
    board = req.boards_dir / "example" / "board.yaml"
    shared = "sclk: I2C_SCLK, mosi: I2C_SDAT,"
    _edit(board, "sclk: ADXL_SCLK, mosi: ADXL_SDI,", shared)
    eep = "  EEP: {kind: i2c, instance: 1, base: 0x8000C100}\n  ACCEL:"
    _edit(req.platform_file, "  ACCEL:", eep)
    platform = yaml.safe_load(req.platform_file.read_text(encoding="utf-8"))
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    texts = [str(f) for f in found if f.rule == "V25"]
    check(any("I2C_SCLK" in t and "EEP" in t and "ACCEL" in t for t in texts))
    check(any("I2C_SDAT" in t for t in texts))
