"""Tests of the RGMII mode of the `eth` kind: top, clocks and `.sdc`."""

from pathlib import Path

import yaml
from peripherals_support import request
from support import check, check_equal, check_in, check_not_in

from riscv_tools.board_check import check_platform
from riscv_tools.board_clocks.eth import eth_requests
from riscv_tools.board_generate import Generated, generate
from riscv_tools.memory_map import kinds
from riscv_tools.memory_map.platform_format import normalize


def _generated(tmp_path: Path, kind: str = "eth_rgmii") -> Generated:
    """Generate the RGMII example."""
    return generate(request(tmp_path, kind))


def _text(result: Generated, suffix: str) -> str:
    """Join the lines of the generated file with the suffix."""
    name = next(n for n in result.files if n.endswith(suffix))
    return " ".join(result.files[name].split())


def test_the_kind_has_a_mii_and_an_rgmii_entity() -> None:
    """`mode` picks the entity and defaults to MII."""
    eth = kinds.EXTERNAL["eth"]
    check_equal(eth.variant_field, "mode")
    mii = eth.variant({"kind": "eth"})
    rgmii = eth.variant({"kind": "eth", "mode": "rgmii"})
    check(mii is not None and rgmii is not None)
    check_equal(mii.entity if mii else "", "eth")
    check_equal(rgmii.entity if rgmii else "", "eth_rgmii_mac")


def test_rgmii_asks_the_pll_for_the_two_transmit_clocks() -> None:
    """125 MHz free and 125 MHz a quarter of a cycle later."""
    item = {"name": "E", "kind": "eth", "mode": "rgmii", "base": 0x8000E000}
    asked = eth_requests({"peripherals": [item]})
    check_equal([a[0] for a in asked], ["eth_tx", "eth_tx_dly"])
    check_equal([a[2] for a in asked], [0, 2000])


def test_an_rgmii_without_the_shift_asks_for_one_clock() -> None:
    """The PHY that delays TXC needs only the free clock."""
    item = {
        "name": "E",
        "kind": "eth",
        "mode": "rgmii",
        "shifted_txc": False,
        "base": 0x8000E000,
    }
    asked = eth_requests({"peripherals": [item]})
    check_equal([a[0] for a in asked], ["eth_tx"])


def test_mii_asks_for_no_clock() -> None:
    """The MII example keeps its clock plan."""
    item = {"name": "E", "kind": "eth", "base": 0x8000E000}
    check_equal(eth_requests({"peripherals": [item]}), [])


def test_the_top_instantiates_the_rgmii_mac(tmp_path: Path) -> None:
    """The entity, its generics, the pins and the two PLL clocks."""
    text = _text(_generated(tmp_path), "_top.vhd")
    check_in("u_eth0 : entity work.eth_rgmii_mac", text)
    check_in("clk_freq_hz => 50000000", text)
    check_in("shifted_txc => true", text)
    check_in("i_tx_clk => clk_eth_tx, i_tx_clk_dly => clk_eth_tx_dly", text)
    check_in("o_rgmii_txc => ENET1_GTX_CLK", text)
    check_in("o_rgmii_txd => ENET1_TX_DATA", text)
    check_in("o_rgmii_tx_ctl => ENET1_TX_EN", text)
    check_in("i_rgmii_rxc => ENET1_RX_CLK", text)
    check_in("i_rgmii_rxd => ENET1_RX_DATA", text)
    check_in("i_rgmii_rx_ctl => ENET1_RX_DV", text)
    check_in("o_phy_rst_n => ENET1_RST_N", text)
    check_in("ENET1_MDIO <= eth0_mdio_out when eth0_mdio_out_oe = '1'", text)
    check_in("signal clk_eth_tx, clk_eth_tx_dly : std_logic;", text)
    check_in("outclk_4 => clk_eth_tx_dly", text)
    check_not_in("i_mii_", text)


def test_the_clock_that_delays_is_dropped_when_the_phy_delays(
    tmp_path: Path,
) -> None:
    """With `shifted_txc` false the MAC takes the free clock twice."""
    req = request(tmp_path, "eth_rgmii")
    req.platform_file.write_text(
        req.platform_file.read_text(encoding="utf-8").replace(
            "shifted_txc: true", "shifted_txc: false"
        ),
        encoding="utf-8",
    )
    text = _text(generate(req), "_top.vhd")
    check_in("shifted_txc => false", text)
    check_in("i_tx_clk => clk_eth_tx, i_tx_clk_dly => clk_eth_tx", text)
    check_not_in("clk_eth_tx_dly", text)


def test_the_pll_has_the_125_mhz_outputs(tmp_path: Path) -> None:
    """The generated PLL makes both transmit clocks."""
    result = _generated(tmp_path)
    pll = _text(result, "_pll.v")
    check_in("outclk_3", pll)
    check_in("outclk_4", pll)


def test_the_sdc_makes_the_ethernet_clocks_asynchronous(
    tmp_path: Path,
) -> None:
    """RXC is an input clock and GTX_CLK a generated one."""
    sdc = _text(_generated(tmp_path), ".sdc")
    check_in("create_clock -name ENET1_RX_CLK -period 8.000", sdc)
    check_in("create_generated_clock -name ENET1_GTX_CLK_pin", sdc)
    check_in("set_clock_groups -asynchronous", sdc)
    check_in("set_false_path -to [get_ports {ENET1_MDC}]", sdc)


def test_the_crossing_bound_ignores_the_ethernet_clocks(
    tmp_path: Path,
) -> None:
    """The core to memory bound stays the least SoC period."""
    sdc = _text(_generated(tmp_path), ".sdc")
    check_in("set_max_delay -from $mem_clocks -to $core_clocks 10", sdc)
    check(" 8 " not in sdc.split("set_max_delay")[1][:60])


def test_a_mii_platform_has_no_ethernet_clock(tmp_path: Path) -> None:
    """The MII example gets no PLL output and no constraint."""
    result = generate(request(tmp_path, "eth"))
    check_not_in("clk_eth_tx", _text(result, "_top.vhd"))
    check_not_in("GTX_CLK", _text(result, ".sdc"))


def test_a_board_copy_without_gtx_clk_is_refused_for_rgmii(
    tmp_path: Path,
) -> None:
    """The MII copy of the role cannot serve an RGMII peripheral."""
    req = request(tmp_path, "eth_rgmii")
    req.platform_file.write_text(
        req.platform_file.read_text(encoding="utf-8").replace(
            "instance: 1, ", "instance: 0, "
        ),
        encoding="utf-8",
    )
    platform = yaml.safe_load(req.platform_file.read_text(encoding="utf-8"))
    normalize(platform, req.platform_file)
    found = check_platform(platform, tmp_path, accept_inferred_pins=True)
    check(any(f.rule == "V24" and "gtx_clk" in str(f) for f in found))
