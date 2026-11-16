"""Tests of the top of a board with external peripherals."""

from pathlib import Path

import pytest
from peripherals_support import GENERATED, request
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_generate import generate
from riscv_tools.board_inputs import InputError


def _top(tmp_path: Path, kind: str) -> tuple[str, list[str]]:
    """Generate an example and give the top and the warnings."""
    result = generate(request(tmp_path, kind))
    text = next(t for n, t in result.files.items() if n.endswith("_top.vhd"))
    return " ".join(text.split()), result.warnings


@pytest.mark.parametrize("kind", GENERATED)
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
    for generic in (
        "filter_cycles => 16",
        "inhibit_cycles => 12000",
        "timeout_cycles => 2000000",
        "packet_timeout_cycles => 10000000",
    ):
        check_in(generic, fast)


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
    """Each chip has its entity, the ADC with its pin."""
    text, warnings = _top(tmp_path, "adc")
    check_in("u_adc0 : entity work.adc128s022", text)
    check_in("o_adc_saddr => ADC_SADDR", text)
    check_in("u_adc1 : entity work.ltc2308", text)
    check_in("o_adc_convst => ADC_CONVST", text)
    check_in("u_adc2 : entity work.max10_adc_shell", text)
    check_in("i_adc_clk_10 => ADC_CLK_10", text)
    check_in("o_irq => ext_irq(ADC2_EXT_POS)", text)
    check_equal([w for w in warnings if "ADC2" in w], [])


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


def _sdc(tmp_path: Path, kind: str) -> str:
    """Generate an example and give its constraints."""
    result = generate(request(tmp_path, kind))
    return next(t for n, t in result.files.items() if n.endswith(".sdc"))


def test_the_wifi_wires_control_spi_and_uart(tmp_path: Path) -> None:
    """GPIO0 is tri-stated by the enable, the rest goes to the pins."""
    text, warnings = _top(tmp_path, "wifi")
    check_in("u_wifi : entity work.wifi", text)
    for generic in (
        "clock_hz => 50000000",
        "reset_pulse_ms => 20",
        "spi_reset_sclk_hz => 2000000",
        "uart_baud_limit => 15049",
        "run_at_reset => false",
        "has_flow_control => true",
    ):
        check_in(generic, text)
    for formal, pin in (
        ("o_wm_reset_n", "WM_RESET_N"),
        ("i_wm_ack", "WM_ACK"),
        ("o_wm_sck", "WM_SCK"),
        ("o_wm_copi", "WM_COPI"),
        ("i_wm_cipo", "WM_CIPO"),
        ("o_wm_cs_n", "WM_CS_N"),
        ("i_wm_tx", "WM_TX"),
        ("o_wm_rx", "WM_RX"),
        ("i_wm_rts", "WM_RTS"),
        ("o_wm_cts", "WM_CTS"),
    ):
        check_in(f"{formal} => {pin}", text)
    check_in("WM_GPIO0 <= wifi_wm_gpio0 when wifi_wm_gpio0_oe = '1'", text)
    check_in("i_address => ext_addr(4 downto 0)", text)
    check_in("o_irq => ext_irq(WIFI_EXT_POS)", text)
    check_equal([w for w in warnings if "WIFI" in w], [])


def test_the_wifi_without_spi_and_uart_pins_parks_the_lines(
    tmp_path: Path,
) -> None:
    """Outputs stay open and inputs rest at their idle level."""
    req = request(tmp_path, "wifi")
    board = req.boards_dir / "example" / "board.yaml"
    board.write_text(
        board.read_text(encoding="utf-8").replace(
            ", sck: WM_SCK, copi: WM_COPI, cipo: WM_CIPO, cs_n: WM_CS_N"
            ", tx: WM_TX, rx: WM_RX, rts: WM_RTS, cts: WM_CTS",
            "",
        ),
        encoding="utf-8",
    )
    top = " ".join(
        next(
            t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
        ).split()
    )
    for tie in (
        "o_wm_sck => open",
        "o_wm_copi => open",
        "i_wm_cipo => '0'",
        "o_wm_cs_n => open",
        "i_wm_tx => '1'",
        "o_wm_rx => open",
        "i_wm_rts => '0'",
        "o_wm_cts => open",
    ):
        check_in(tie, top)


def test_the_wifi_pins_have_no_timing_requirement(tmp_path: Path) -> None:
    """Every pin of the module is cut from the core clock."""
    sdc = _sdc(tmp_path, "wifi")
    check_in("set_false_path -from [get_ports {WM_ACK}]", sdc)
    check_in("set_false_path -to   [get_ports {WM_SCK}]", sdc)
    check_in("set_false_path -to   [get_ports {WM_GPIO0}]", sdc)


def test_the_camera_samples_the_lanes_in_a_ddr_register(
    tmp_path: Path,
) -> None:
    """The entity gets the camera clock and two bits of each lane."""
    text, warnings = _top(tmp_path, "mipi")
    for found in (
        "u_camera : entity work.mipi generic map (lanes => 2",
        "fb_line_bytes => 512",
        "default_dt => 42",
        "i_mipi_clk => MIPI_CLK",
        "i_mipi_early => camera_early",
        "i_mipi_late => camera_late",
        "u_camera_ddr : entity work.mipi_ddr_in generic map (width => 2) "
        "port map (i_clk => MIPI_CLK, i_d => MIPI_D, "
        "o_q_early => camera_early, o_q_late => camera_late);",
        "i_address => ext_addr(3 downto 0)",
        "o_irq => ext_irq(CAMERA_EXT_POS)",
    ):
        check_in(found, text)
    check_equal([w for w in warnings if "CAMERA" in w], [])


def test_the_camera_i2c_is_the_third_copy_of_the_i2c_role(
    tmp_path: Path,
) -> None:
    """The entity has no I2C, so the bus is an `i2c` peripheral."""
    text, _ = _top(tmp_path, "mipi")
    check_in("u_camera_i2c : entity work.i2c_master", text)
    check_in("MIPI_SCL <= '0' when camera_i2c_scl_low = '1'", text)
    check_in("MIPI_SDA <= '0' when camera_i2c_sda_low = '1'", text)


def test_the_lanes_follow_the_width_of_the_pin(tmp_path: Path) -> None:
    """Without `lanes` the generic is the number of bits of `d`."""
    req = request(tmp_path, "mipi")
    req.platform_file.write_text(
        req.platform_file.read_text(encoding="utf-8").replace(
            "lanes: 2, ", ""
        ),
        encoding="utf-8",
    )
    top = " ".join(
        next(
            t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_in("lanes => 2", top)


def test_lanes_that_differ_from_the_pin_width_are_refused(
    tmp_path: Path,
) -> None:
    """The generator stops, and `check-boards` reports it as V24."""
    req = request(tmp_path, "mipi")
    req.platform_file.write_text(
        req.platform_file.read_text(encoding="utf-8").replace(
            "lanes: 2", "lanes: 1"
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="lanes 1 differs from the 2 lanes"):
        generate(req)


def test_the_camera_clock_is_constrained_and_async_to_the_soc(
    tmp_path: Path,
) -> None:
    """The LVDS clock gets a clock of its own, apart from the SoC."""
    sdc = _sdc(tmp_path, "mipi")
    check_in("create_clock -name MIPI_CLK -period 5.000", sdc)
    check_in("set_clock_groups -asynchronous", sdc)
    check_in("-group [get_clocks {MIPI_CLK}]", sdc)


def test_the_tmds_output_wires_pairs_clocks_and_hot_plug(
    tmp_path: Path,
) -> None:
    """The pairs, the three clocks and `hpd` reach the wrapper."""
    text, warnings = _top(tmp_path, "hdmi_tmds")
    for found in (
        "u_hdmi : entity work.hdmi_tmds_tx generic map (fb_width => 320",
        "o_tmds_d => TMDS",
        "o_tmds_clk => TMDS_CLK",
        "i_hpd => TMDS_HPD",
        "i_pixel_clk => clk_pixel",
        "i_serial_clk => clk_pixel_x5",
        "i_byteena => ext_byteena",
        "i_address => ext_addr(15 downto 0)",
        "o_irq => ext_irq(HDMI_EXT_POS)",
    ):
        check_in(found, text)
    check_not_in("i_read => ext_re(HDMI_EXT_POS)", text)
    wrapper = text.split("u_hdmi_ddc", maxsplit=1)[0].split("u_hdmi :")[1]
    check_not_in("clk_freq", wrapper)
    check_equal([w for w in warnings if "HDMI" in w], [])


def test_the_tmds_ddc_is_a_separate_i2c_master(tmp_path: Path) -> None:
    """The wrapper has no DDC, so `scl` and `sda` go to an `i2c`."""
    text, _ = _top(tmp_path, "hdmi_tmds")
    check_in("u_hdmi_ddc : entity work.i2c_master", text)
    check_in("TMDS_SCL <= '0' when hdmi_ddc_scl_low = '1'", text)
    check_in("TMDS_SDA <= '0' when hdmi_ddc_sda_low = '1'", text)
    check_not_in("i_i2c_scl", text.split("u_hdmi_ddc", maxsplit=1)[0])


def test_the_tmds_without_hpd_ties_it_to_zero(tmp_path: Path) -> None:
    """A board role without `hpd` leaves the monitor as absent."""
    req = request(tmp_path, "hdmi_tmds")
    board = req.boards_dir / "example" / "board.yaml"
    board.write_text(
        board.read_text(encoding="utf-8").replace(", hpd: TMDS_HPD", ""),
        encoding="utf-8",
    )
    top = " ".join(
        next(
            t for n, t in generate(req).files.items() if n.endswith("_top.vhd")
        ).split()
    )
    check_in("i_hpd => '0'", top)
    check_not_in("i_hpd => TMDS_HPD", top)


def test_the_tmds_pins_have_no_timing_requirement(tmp_path: Path) -> None:
    """The pairs and `hpd` are cut from the core clock."""
    sdc = _sdc(tmp_path, "hdmi_tmds")
    check_in("set_false_path -to   [get_ports {TMDS[*]}]", sdc)
    check_in("set_false_path -to   [get_ports {TMDS_CLK}]", sdc)
    check_in("set_false_path -from [get_ports {TMDS_HPD}]", sdc)
