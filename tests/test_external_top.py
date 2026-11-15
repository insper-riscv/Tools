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


def test_ps2_times_follow_the_core_clock(tmp_path: Path) -> None:
    """The cycle counts are the ones of 50 MHz, scaled to the core."""
    (tmp_path / "a").mkdir()
    base, _ = _top(tmp_path / "a", "ps2")
    check_in("filter_cycles => 8", base)
    check_in("inhibit_cycles => 6000", base)
    check_in("init_timeout_cycles => 100000000", base)
    (tmp_path / "b").mkdir()
    req = request(tmp_path / "b", "ps2")
    text = req.platform_file.read_text(encoding="utf-8")
    req.platform_file.write_text(
        text.replace("core: {mhz: 50,", "core: {mhz: 100,"), encoding="utf-8"
    )
    fast = " ".join(
        next(
            t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_in("filter_cycles => 16", fast)
    check_in("inhibit_cycles => 12000", fast)
    check_in("timeout_cycles => 2000000", fast)
    check_in("packet_timeout_cycles => 10000000", fast)


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


def test_hdmi_waits_for_the_pixel_clock(tmp_path: Path) -> None:
    """Without a pixel clock the instance is left out with a warning."""
    text, warnings = _top(tmp_path, "hdmi")
    check(any("HDMI" in w and "pixel clock" in w for w in warnings))
    check_in("ext_irq(HDMI_EXT_POS) <= '0';", text)


def test_video_gets_the_pixel_clock_and_its_generics(tmp_path: Path) -> None:
    """The video takes a PLL output and the plan as generics."""
    result = generate(request(tmp_path, "video"))
    text = " ".join(
        next(
            t for n, t in result.files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_in("signal clk_pixel : std_logic;", text)
    check_in("outclk_3 => clk_pixel", text)
    check_in("u_video : entity work.video generic map (", text)
    check_in('pixel_format => "indexed"', text)
    check_in("fb_width => 320", text)
    check_in("scale => 2", text)
    check_in("h_visible => 640", text)
    check_in("i_pixel_clk => clk_pixel", text)
    check_equal([w for w in result.warnings if "pixel clock" in w], [])
    sdc = next(t for n, t in result.files.items() if n.endswith(".sdc"))
    check_in("set_false_path -from $core_clocks -to $pixel_clocks", sdc)
    check_in("set_false_path -from $pixel_clocks -to $core_clocks", sdc)


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


def test_hdmi_audio_wires_the_i2s_pins_and_its_generics(
    tmp_path: Path,
) -> None:
    """The I2S entity gets the four pins and each field as a generic."""
    text, _ = _top(tmp_path, "hdmi_audio")
    check_in("u_hdmi_audio : entity work.hdmi_audio", text)
    for generic in (
        "clk_freq => 50000000",
        "sample_rate => 44100",
        "mclk_ratio => 128",
        "word_bits => 16",
        "tx_fifo_depth => 64",
        "has_tone => false",
        "tone_freq => 440",
        "tone_amp => 4096",
        "autostart => true",
    ):
        check_in(generic, text)
    for formal, pin in (
        ("o_mclk", "HDMI_MCLK"),
        ("o_sclk", "HDMI_SCLK"),
        ("o_lrclk", "HDMI_LRCLK"),
        ("o_i2s0", "HDMI_I2S0"),
    ):
        check_in(f"{formal} => {pin}", text)
    check_in("o_irq => ext_irq(HDMI_AUDIO_EXT_POS)", text)
    check_in("i_address => ext_addr(3 downto 0)", text)


def test_hdmi_audio_is_left_out_when_the_board_lacks_the_role(
    tmp_path: Path,
) -> None:
    """With `need: optional` a board without the I2S pins skips it."""
    req = request(tmp_path, "hdmi_audio")
    board = req.boards_dir / "example" / "board.yaml"
    board.write_text(
        board.read_text(encoding="utf-8").replace(
            "  hdmi_audio: {mclk: HDMI_MCLK, sclk: HDMI_SCLK, "
            "lrclk: HDMI_LRCLK, i2s0: HDMI_I2S0}\n",
            "",
        ),
        encoding="utf-8",
    )
    req.platform_file.write_text(
        req.platform_file.read_text(encoding="utf-8").replace(
            "kind: hdmi_audio,", "kind: hdmi_audio, need: optional,"
        ),
        encoding="utf-8",
    )
    result = generate(req)
    top = " ".join(
        next(
            t for n, t in result.files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_not_in("entity work.hdmi_audio", top)
    check(any("HDMI_AUDIO" in w and "omitted" in w for w in result.warnings))


def test_the_uart_wires_the_flow_control_lines(tmp_path: Path) -> None:
    """RTS and CTS reach the pins and the queue depths are generics."""
    text, _ = _top(tmp_path, "uart")
    check_in("u_serial : entity work.uart", text)
    for generic in (
        "has_flow_control => true",
        "rx_fifo_depth => 32",
        "tx_fifo_depth => 8",
        "baud_freq => 576",
        "baud_limit => 15049",
    ):
        check_in(generic, text)
    check_in("i_uart_rx => SER_RXD", text)
    check_in("o_uart_tx => SER_TXD", text)
    check_in("i_uart_cts => SER_CTS", text)
    check_in("o_uart_rts => SER_RTS", text)
    check_in("i_address => ext_addr(1 downto 0)", text)


def test_the_uart_without_flow_pins_ties_cts_low(tmp_path: Path) -> None:
    """A board with only RX and TX leaves CTS at '0' and RTS open."""
    req = request(tmp_path, "uart")
    board = req.boards_dir / "example" / "board.yaml"
    board.write_text(
        board.read_text(encoding="utf-8").replace(
            ", cts: SER_CTS, rts: SER_RTS", ""
        ),
        encoding="utf-8",
    )
    top = " ".join(
        next(
            t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_in("i_uart_cts => '0'", top)
    check_in("o_uart_rts => open", top)


def test_the_eth_mac_and_mdio_fields_are_generics(tmp_path: Path) -> None:
    """The MAC and the MDIO master each take their own generics."""
    text, _ = _top(tmp_path, "eth")
    for generic in (
        "phy_addr => 16",
        "mdc_freq_hz => 1000000",
        "poll_cycles => 1000",
        "tx_buffer_addr_bits => 10",
        "rx_buffer_addr_bits => 8",
        "rx_fifo_addr_bits => 5",
        "sync_stages => 3",
        "reset_cycles => 32",
    ):
        check_in(generic, text)
