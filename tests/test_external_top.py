"""Tests of the top of a board with external peripherals."""

from pathlib import Path

import pytest
from peripherals_support import EXAMPLES, request
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_generate import generate


def _top(tmp_path: Path, kind: str) -> tuple[str, list[str]]:
    """Generate an example and give the top and the warnings."""
    result = generate(request(tmp_path, kind))
    text = next(t for n, t in result.files.items() if n.endswith("_top.vhd"))
    return " ".join(text.split()), result.warnings


@pytest.mark.parametrize("kind", EXAMPLES)
def test_every_example_generates_its_instance(
    kind: str, tmp_path: Path
) -> None:
    """The top instantiates each peripheral next to the SoC."""
    text, _ = _top(tmp_path, kind)
    check_in("soc_inst : entity work.soc", text)
    check_in("ext_indices => EXT_INDICES", text)
    check_in("ext_irq_ids => EXT_IRQ_IDS", text)
    check_in("o_ext_we => ext_we", text)
    check_in("i_ext_irq => ext_irq", text)
    check_in("u_", text)
    check_in("o_ext_re => ext_re", text)


def test_ps2_keyboard_and_mouse_take_the_two_channels(
    tmp_path: Path,
) -> None:
    """Each PS/2 peripheral uses the pins of its own copy."""
    text, warnings = _top(tmp_path, "ps2")
    check_in("u_kbd : entity work.ps2_keyboard", text)
    check_in("io_ps2_clk => PS2_CLK, io_ps2_dat => PS2_DAT", text)
    check_in("u_mouse : entity work.ps2_mouse_top", text)
    check_in("io_ps2_clk => PS2_CLK2, io_ps2_dat => PS2_DAT2", text)
    check_in("i_write => ext_we(KBD_EXT_POS)", text)
    check_in("o_irq => ext_irq(MOUSE_EXT_POS)", text)
    check_equal([w for w in warnings if "peripheral" in w], [])


def test_the_sd_card_in_spi_mode_uses_clk_cmd_and_dat(
    tmp_path: Path,
) -> None:
    """MOSI goes on CMD, MISO is DAT(0) and CS is DAT(3)."""
    text, _ = _top(tmp_path, "sd_spi")
    check_in(
        "u_sd : entity work.sd_spi generic map (clock_hz => 50000000)", text
    )
    check_in("SD_CMD <= sd_mosi;", text)
    check_in("SD_DAT <= (3 => sd_cs_n, others => 'Z');", text)
    check_in("sd_miso <= SD_DAT(0);", text)
    check_in("o_sd_sclk => SD_CLK", text)
    check_not_in("i_read => ext_re(SD_EXT_POS), i_read", text)


def test_the_i2c_pins_are_open_drain(tmp_path: Path) -> None:
    """The bus pulls the pin low or lets it go."""
    text, _ = _top(tmp_path, "i2c")
    check_in("EEP_I2C_SCLK <= '0' when eeprom_scl_low = '1' else 'Z';", text)
    check_in("I2C_SDAT <= '0' when audio_i2c_sda_low = '1' else 'Z';", text)


def test_the_usb_bridge_gets_its_polarity_and_tristate(
    tmp_path: Path,
) -> None:
    """The HPI data bus is tri-stated with the enable of the entity."""
    text, _ = _top(tmp_path, "usb")
    check_in("int_active_high => false", text)
    check_in(
        "OTG_DATA <= usb_otg_data when usb_otg_data_oe = '1' "
        "else (others => 'Z');",
        text,
    )
    check_in('usb_int <= "0" & OTG_INT;', text)


def test_the_adc_picks_the_entity_by_chip(tmp_path: Path) -> None:
    """Each chip has its entity and the internal ADC is left out."""
    text, warnings = _top(tmp_path, "adc")
    check_in("u_adc0 : entity work.adc128s022", text)
    check_in("o_adc_saddr => ADC_SADDR", text)
    check_in("u_adc1 : entity work.ltc2308", text)
    check_in("o_adc_convst => ADC_CONVST", text)
    check_not_in("max10_adc", text)
    check(any("ADC2" in w and "vendor IP" in w for w in warnings))
    check_in("ext_irq(ADC2_EXT_POS) <= '0';", text)


def test_video_and_hdmi_wait_for_the_pixel_clock(tmp_path: Path) -> None:
    """Without a pixel clock the instance is left out with a warning."""
    for kind, name in (("video", "VIDEO"), ("hdmi", "HDMI")):
        (tmp_path / kind).mkdir()
        text, warnings = _top(tmp_path / kind, kind)
        check(any(name in w and "pixel clock" in w for w in warnings))
        check_in(f"ext_irq({name}_EXT_POS) <= '0';", text)


def test_a_platform_without_external_peripherals_has_no_bus(
    tmp_path: Path,
) -> None:
    """The generated top is the same as before without the kinds."""
    req = request(tmp_path, "ir")
    text = req.platform_file.read_text(encoding="utf-8")
    req.platform_file.write_text(
        text.replace("  IR: {kind: ir, base: 0x80009000}\n", ""),
        encoding="utf-8",
    )
    top = next(
        t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
    )
    check_not_in("ext_", top)
