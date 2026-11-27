"""Instancia no topo os periféricos externos da plataforma.

Cada entrada de `peripherals` com um `kind` externo (ver
`riscv_tools.memory_map.kinds`) vira uma instância de uma entidade do
`Peripherals`, ligada aos pinos do papel da placa e a um barramento
externo do SoC.

O barramento externo é o contrato com o SoC. Os generics `ext_indices`
e `ext_irq_ids` recebem as tabelas `EXT_INDICES` e `EXT_IRQ_IDS` do
pacote do mapa, e `ext_addr_width` a largura do endereço de palavra.
As portas do SoC são `o_ext_addr`, `o_ext_wdata`, `o_ext_byteena`,
`o_ext_we` e `o_ext_re` (um bit por periférico, na ordem das tabelas),
`i_ext_rdata` (32 bits por periférico) e `i_ext_irq`. O periférico de
posição `<NOME>_EXT_POS` lê e escreve as fatias dele.

Os pinos bidirecionais (`inout`) saem por `'Z'` com a habilitação da
entidade, e o open drain do I2C leva o `'0'` ou solta o pino.
"""

from dataclasses import dataclass, field
from typing import Any

from riscv_tools.board_inputs import InputError
from riscv_tools.board_ports import Port
from riscv_tools.memory_map.board_gpio import board_gpio_list
from riscv_tools.memory_map.external import external_list
from riscv_tools.memory_map.kind_fields import FieldSpec
from riscv_tools.memory_map.kinds import (
    EXTERNAL,
    MISSING_ENTITIES,
    PIXEL_ENTITIES,
    SERIAL_ENTITIES,
    Variant,
)
from riscv_tools.top_generator.board_gpio import gpio_address_bits, gpio_lines
from riscv_tools.top_generator.spec import TopSpec

# Entidades sem o sinal `i_read` e as que têm `i_byteena` e relógio de
# pixel.
NO_READ = frozenset(
    {"video", "hdmi_tx", "hdmi_tmds_tx", "adc128s022", "ltc2308", "adxl345"}
)
WITH_PIXEL = PIXEL_ENTITIES
_WORD = 32
_HZ = 1_000_000_000
# Os generics de tempo do PS/2 contam ciclos, e os valores padrão da
# entidade valem para um relógio de 50 MHz (160 ns de filtro, 120 us de
# inibição, 20 ms de limite do quadro, 2 s de inicialização do mouse e
# 100 ms de limite do pacote). Cada um é refeito para o relógio do
# núcleo.
_PS2_BASE_HZ = 50_000_000
_PS2_CYCLES = {
    "filter_cycles": 8,
    "inhibit_cycles": 6000,
    "timeout_cycles": 1_000_000,
}
_PS2_MOUSE_CYCLES = {
    "init_timeout_cycles": 100_000_000,
    "packet_timeout_cycles": 5_000_000,
}
_PS2_TABLES = {
    "ps2_keyboard": _PS2_CYCLES,
    "ps2_mouse_top": {**_PS2_CYCLES, **_PS2_MOUSE_CYCLES},
}


@dataclass
class Wiring:
    """Ligações de uma entidade aos pinos.

    Attributes
    ----------
    maps : list of str
        Associações do `port map` além do barramento.
    signals : list of str
        Sinais locais que a ligação declara.
    body : list of str
        Atribuições concorrentes dos pinos.
    """

    maps: list[str] = field(default_factory=list[str])
    signals: list[str] = field(default_factory=list[str])
    body: list[str] = field(default_factory=list[str])


@dataclass
class ExternalTop:
    """O que os periféricos externos acrescentam ao topo.

    Attributes
    ----------
    generics : list of str
        Generics do SoC.
    ports : list of str
        Associações das portas do barramento externo do SoC.
    signals : list of str
        Declarações da arquitetura.
    body : list of str
        As instâncias e as atribuições.
    notes : list of str
        Avisos dos periféricos que ficaram fora.
    """

    generics: list[str] = field(default_factory=list[str])
    ports: list[str] = field(default_factory=list[str])
    signals: list[str] = field(default_factory=list[str])
    body: list[str] = field(default_factory=list[str])
    notes: list[str] = field(default_factory=list[str])


def _type(port: Port) -> str:
    """Escreve o tipo VHDL de um sinal com a largura de uma porta."""
    if not port.vector:
        return "std_logic"
    return f"std_logic_vector({port.width - 1} downto 0)"


def _direct(formal: str, port: Port | None, tie: str = "") -> Wiring:
    """Liga um formal direto a uma porta, ou a um valor fixo.

    Parameters
    ----------
    formal : str
        A porta da entidade.
    port : Port or None
        A porta da placa; `None` quando o pino é opcional e ausente.
    tie : str
        O que ligar sem pino; vazio deixa `open`.

    Returns
    -------
    Wiring
        A associação.
    """
    actual = port.name if port else (tie or "open")
    return Wiring([f"{formal} => {actual}"])


def _tri(inst: str, pair: tuple[str, str, str], port: Port | None) -> Wiring:
    """Liga uma porta `inout` a uma saída com habilitação e uma entrada.

    Parameters
    ----------
    inst : str
        O rótulo da instância, prefixo dos sinais locais.
    pair : tuple of (str, str, str)
        Os formais de saída, de habilitação e de entrada.
    port : Port or None
        A porta `inout` da placa.

    Returns
    -------
    Wiring
        Sinais, associações e a atribuição de `'Z'`.
    """
    out, enable, back = pair
    if port is None:
        return Wiring([f"{back} => '0'"])
    stem = f"{inst}_{out[2:]}"
    kind = _type(port)
    sigs = [f"signal {stem}, {stem}_in : {kind};"]
    oe = f"{stem}_oe"
    if port.vector:
        sigs.append(f"signal {oe} : std_logic;")
        drive = f"{port.name} <= {stem} when {oe} = '1' else (others => 'Z');"
    else:
        sigs.append(f"signal {oe} : std_logic;")
        drive = f"{port.name} <= {stem} when {oe} = '1' else 'Z';"
    return Wiring(
        [f"{out} => {stem}", f"{enable} => {oe}", f"{back} => {stem}_in"],
        sigs,
        [drive, f"{stem}_in <= {port.name};"],
    )


def _open_drain(inst: str, formals: tuple[str, str], port: Port) -> Wiring:
    """Liga um pino open drain: baixo leva `'0'`, senão solta.

    Parameters
    ----------
    inst : str
        O rótulo da instância.
    formals : tuple of (str, str)
        O formal que pede o nível baixo e o de leitura.
    port : Port
        A porta `inout` da placa.

    Returns
    -------
    Wiring
        Sinais, associações e a atribuição.
    """
    low, back = formals
    stem = f"{inst}_{low[2:]}"
    return Wiring(
        [f"{low} => {stem}", f"{back} => {stem}_in"],
        [f"signal {stem}, {stem}_in : std_logic;"],
        [
            f"{port.name} <= '0' when {stem} = '1' else 'Z';",
            f"{stem}_in <= {port.name};",
        ],
    )


def _merge(parts: list[Wiring]) -> Wiring:
    """Reúne as ligações de uma entidade em uma só."""
    found = Wiring()
    for part in parts:
        found.maps += part.maps
        found.signals += part.signals
        found.body += part.body
    return found


def _ps2(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o PS/2: duas linhas `inout` direto."""
    return Wiring(
        [f"io_ps2_clk => {p['clk'].name}", f"io_ps2_dat => {p['dat'].name}"]
    )


def _sd_spi(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o cartão no modo SPI (MOSI em CMD, MISO e CS em DAT)."""
    dat, cmd = p["dat"], p["cmd"]
    mosi, cs, miso = f"{inst}_mosi", f"{inst}_cs_n", f"{inst}_miso"
    return Wiring(
        [
            f"o_sd_sclk => {p['clk'].name}",
            f"o_sd_mosi => {mosi}",
            f"i_sd_miso => {miso}",
            f"o_sd_cs_n => {cs}",
        ],
        [f"signal {mosi}, {cs}, {miso} : std_logic;"],
        [
            f"{cmd.name} <= {mosi};",
            f"{dat.name} <= (3 => {cs}, others => 'Z');",
            f"{miso} <= {dat.name}(0);",
        ],
    )


def _sd_native(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o cartão de 4 bits: CMD e DAT com habilitação."""
    dat = p["dat"]
    stem = f"{inst}_dat"
    sigs = [
        f"signal {stem}, {stem}_in, {stem}_oe : std_logic_vector(3 downto 0);"
    ]
    parts = [
        Wiring([f"o_sd_clk => {p['clk'].name}"]),
        _tri(inst, ("o_sd_cmd", "o_sd_cmd_oe", "i_sd_cmd"), p["cmd"]),
        Wiring(
            [
                f"o_sd_dat => {stem}",
                f"o_sd_dat_oe => {stem}_oe",
                f"i_sd_dat => {stem}_in",
            ],
            sigs,
            [
                f"gen_{stem} : for i in 0 to 3 generate",
                f"\t{dat.name}(i) <= {stem}(i) when {stem}_oe(i) = '1' "
                "else 'Z';",
                "end generate;",
                f"{stem}_in <= {dat.name};",
            ],
        ),
    ]
    return _merge(parts)


def _ir(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o receptor de infravermelho."""
    return _direct("i_irda_rxd", p["rxd"])


def _lcd(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o LCD: dados `inout` com habilitação e os controles."""
    return _merge(
        [
            _tri(
                inst, ("o_lcd_data", "o_lcd_data_oe", "i_lcd_data"), p["data"]
            ),
            _direct("o_lcd_rs", p["rs"]),
            _direct("o_lcd_rw", p["rw"]),
            _direct("o_lcd_en", p["en"]),
            _direct("o_lcd_on", p["power"]),
            _direct("o_lcd_blon", p.get("blon")),
        ]
    )


def _usb(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a ponte USB: barramento HPI e a interrupção do chip."""
    irq = f"{inst}_int"
    parts = [
        _direct("o_otg_cs_n", p["cs_n"]),
        _direct("o_otg_rd_n", p["rd_n"]),
        _direct("o_otg_wr_n", p["wr_n"]),
        _direct("o_otg_rst_n", p["rst_n"]),
        _direct("o_otg_addr", p["addr"]),
        _tri(inst, ("o_otg_data", "o_otg_data_oe", "i_otg_data"), p["data"]),
        _direct("i_otg_dreq", p.get("dreq"), "'0'"),
        _direct("o_otg_dack", p.get("dack")),
        Wiring(
            [f"i_otg_int => {irq}"],
            [f"signal {irq} : std_logic_vector(1 downto 0);"],
            [f'{irq} <= "0" & {p["int"].name};'],
        ),
    ]
    return _merge(parts)


def _i2c(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o mestre I2C: SCL e SDA open drain."""
    return _merge(
        [
            _open_drain(inst, ("o_scl_low", "i_scl"), p["scl"]),
            _open_drain(inst, ("o_sda_low", "i_sda"), p["sda"]),
        ]
    )


def _audio(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o áudio: o FPGA é o mestre dos relógios do codec."""
    return _merge(
        [
            _direct("o_xck", p["xck"]),
            _direct("o_bclk", p["bclk"]),
            _direct("o_adclrck", p["adclrck"]),
            _direct("o_daclrck", p["daclrck"]),
            _direct("o_dacdat", p["dacdat"]),
            _direct("i_adcdat", p["adcdat"]),
            _direct("i_bclk", None, "'0'"),
            _direct("i_adclrck", None, "'0'"),
            _direct("i_daclrck", None, "'0'"),
        ]
    )


def _eth(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o Ethernet MII e o MDIO."""
    return _merge(
        [
            _direct("i_mii_rx_clk", p["rx_clk"]),
            _direct("i_mii_rxd", p["rxd"]),
            _direct("i_mii_rx_dv", p["rx_dv"]),
            _direct("i_mii_rx_er", p["rx_er"]),
            _direct("i_mii_tx_clk", p["tx_clk"]),
            _direct("o_mii_txd", p["txd"]),
            _direct("o_mii_tx_en", p["tx_en"]),
            _direct("o_mii_tx_er", p["tx_er"]),
            _direct("o_mdc", p["mdc"]),
            _tri(inst, ("o_mdio_out", "o_mdio_oe", "i_mdio"), p["mdio"]),
            _direct("i_phy_int_n", p.get("int_n"), "'1'"),
            _direct("o_phy_rst_n", p["rst_n"]),
            _direct("o_tx_speed", None),
        ]
    )


def _eth_rgmii(inst: str, p: dict[str, Port], shifted: bool) -> Wiring:
    """Liga o Ethernet RGMII, com o MDIO.

    Parameters
    ----------
    inst : str
        O rótulo da instância.
    p : dict of {str: Port}
        Os pinos do papel.
    shifted : bool
        Se o `GTX_CLK` sai do relógio deslocado de 90 graus do PLL
        (`clk_eth_tx_dly`) ou do próprio `clk_eth_tx`.

    Returns
    -------
    Wiring
        As associações: relógios de envio do PLL, pinos DDR e MDIO.
    """
    delayed = "clk_eth_tx_dly" if shifted else "clk_eth_tx"
    return _merge(
        [
            Wiring(["i_tx_clk => clk_eth_tx", f"i_tx_clk_dly => {delayed}"]),
            _direct("o_rgmii_txc", p["gtx_clk"]),
            _direct("o_rgmii_txd", p["txd"]),
            _direct("o_rgmii_tx_ctl", p["tx_en"]),
            _direct("i_rgmii_rxc", p["rx_clk"]),
            _direct("i_rgmii_rxd", p["rxd"]),
            _direct("i_rgmii_rx_ctl", p["rx_dv"]),
            _direct("o_mdc", p["mdc"]),
            _tri(inst, ("o_mdio_out", "o_mdio_oe", "i_mdio"), p["mdio"]),
            _direct("i_phy_int_n", p.get("int_n"), "'1'"),
            _direct("o_phy_rst_n", p["rst_n"]),
        ]
    )


def _hdmi(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a saída HDMI e o I2C do ADV7513."""
    parts = [
        _direct("o_tx_d", p["d"]),
        _direct("o_tx_clk", p["clk"]),
        _direct("o_tx_de", p["de"]),
        _direct("o_tx_hs", p["hs"]),
        _direct("o_tx_vs", p["vs"]),
        _direct("i_tx_int", p["int"]),
    ]
    for line in ("scl", "sda"):
        pair = (f"o_i2c_{line}_out", f"o_i2c_{line}_oe", f"i_i2c_{line}")
        parts.append(_tri(inst, pair, p[line]))
    return _merge(parts)


def _hdmi_tmds(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a saída TMDS direta; o DDC fica com um `i2c_master` à parte.

    Os três pares de dados saem em `tmds` e o par de relógio em `clk`
    (o lado positivo; o negativo vem da atribuição de pino diferencial).
    Sem o pino `hpd` a entrada `i_hpd` fica em `'0'`, monitor ausente.
    """
    return _merge(
        [
            _direct("o_tmds_d", p["tmds"]),
            _direct("o_tmds_clk", p["clk"]),
            _direct("i_hpd", p.get("hpd"), "'0'"),
        ]
    )


def _hdmi_audio(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o áudio I2S do transmissor HDMI: só saídas, modo mestre."""
    return _merge(
        [
            _direct("o_mclk", p["mclk"]),
            _direct("o_sclk", p["sclk"]),
            _direct("o_lrclk", p["lrclk"]),
            _direct("o_i2s0", p["i2s0"]),
        ]
    )


def _uart(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a UART serial; RTS e CTS são opcionais.

    Sem o pino `cts` a entrada fica em `'0'` (o outro lado sempre
    aceita bytes) e sem `rts` a saída fica aberta.
    """
    return _merge(
        [
            _direct("i_uart_rx", p["rx"]),
            _direct("o_uart_tx", p["tx"]),
            _direct("i_uart_cts", p.get("cts"), "'0'"),
            _direct("o_uart_rts", p.get("rts")),
        ]
    )


def _max10(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o ADC do MAX 10: o relógio de 10 MHz."""
    return _direct("i_adc_clk_10", p["clk10"])


def _tv(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a captura de TV."""
    return _merge(
        [
            _direct("i_td_clk27", p["clk27"]),
            _direct("i_td_data", p["data"]),
            _direct("o_td_reset_n", p["reset_n"]),
        ]
    )


def _adc128(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o ADC128S022."""
    return _merge(
        [
            _direct("o_adc_cs_n", p["cs_n"]),
            _direct("o_adc_sclk", p["sclk"]),
            _direct("o_adc_saddr", p["saddr"]),
            _direct("i_adc_sdat", p["sdat"]),
        ]
    )


def _ltc(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o LTC2308."""
    return _merge(
        [
            _direct("o_adc_convst", p["convst"]),
            _direct("o_adc_sck", p["sck"]),
            _direct("o_adc_sdi", p["sdi"]),
            _direct("i_adc_sdo", p["sdo"]),
        ]
    )


def _spi(inst: str, p: dict[str, Port], count: int = 1) -> Wiring:
    """Liga o mestre SPI; `cs_n` é fatiado na largura da placa."""
    cs = p["cs_n"]
    sig = f"{inst}_cs"
    picked = f"{sig}({cs.width - 1} downto 0)" if cs.vector else f"{sig}(0)"
    return Wiring(
        [
            f"o_sclk => {p['sclk'].name}",
            f"o_mosi => {p['mosi'].name}",
            f"i_miso => {p['miso'].name}",
            f"o_cs_n => {sig}",
            "o_mosi_oe => open",
        ],
        [f"signal {sig} : std_logic_vector({count - 1} downto 0);"],
        [f"{cs.name} <= {picked};"],
    )


def _adxl(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o ADXL345; sem `miso` lê o dado de volta do pino `mosi`."""
    mosi = p["mosi"]
    miso = p.get("miso")
    sig = f"{inst}_mosi"
    back = miso.name if miso else f"{sig}_in"
    parts = [
        _direct("o_adxl_cs_n", p["cs_n"]),
        _direct("o_adxl_sclk", p["sclk"]),
        _direct("i_adxl_int1", p.get("int1"), "'0'"),
        _tri(inst, ("o_adxl_mosi", "o_adxl_mosi_oe", "i_adxl_miso"), mosi),
    ]
    if miso is not None:
        parts[-1].maps[-1] = f"i_adxl_miso => {back}"
    return _merge(parts)


def _video(_inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a saída VGA; o apagamento e o sincronismo são opcionais."""
    return _merge(
        [
            _direct("o_vga_r", p["r"]),
            _direct("o_vga_g", p["g"]),
            _direct("o_vga_b", p["b"]),
            _direct("o_vga_hs", p["hs"]),
            _direct("o_vga_vs", p["vs"]),
            _direct("o_vga_blank_n", p.get("blank_n")),
            _direct("o_vga_sync_n", p.get("sync_n")),
        ]
    )


def _wifi(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga o módulo Wi-Fi; o SPI e a UART são opcionais.

    O `gpio0` sai com a habilitação da entidade e não é lido de volta.
    Sem pino, uma saída fica aberta e uma entrada fica parada no nível
    de repouso: `cipo` e `rts` em `'0'`, `tx` em `'1'` (linha serial
    ociosa).
    """
    port = p["gpio0"]
    stem = f"{inst}_wm_gpio0"
    gpio0 = Wiring(
        [f"o_wm_gpio0 => {stem}", f"o_wm_gpio0_oe => {stem}_oe"],
        [f"signal {stem}, {stem}_oe : std_logic;"],
        [f"{port.name} <= {stem} when {stem}_oe = '1' else 'Z';"],
    )
    return _merge(
        [
            _direct("o_wm_reset_n", p["reset_n"]),
            gpio0,
            _direct("i_wm_ack", p["ack"]),
            _direct("o_wm_sck", p.get("sck")),
            _direct("o_wm_copi", p.get("copi")),
            _direct("i_wm_cipo", p.get("cipo"), "'0'"),
            _direct("o_wm_cs_n", p.get("cs_n")),
            _direct("i_wm_tx", p.get("tx"), "'1'"),
            _direct("o_wm_rx", p.get("rx")),
            _direct("i_wm_rts", p.get("rts"), "'0'"),
            _direct("o_wm_cts", p.get("cts")),
        ]
    )


def _mipi(inst: str, p: dict[str, Port]) -> Wiring:
    """Liga a câmera MIPI: o relógio e o registrador DDR das lanes.

    A entidade recebe cada lane já amostrada nas duas bordas do relógio
    da câmera, então o topo instancia o registrador DDR de entrada
    entre os pinos e a entidade.
    """
    clk, data = p["clk"], p["d"]
    early, late = f"{inst}_early", f"{inst}_late"
    lanes = f"std_logic_vector({data.width - 1} downto 0)"
    sigs = [f"signal {early}, {late} : {lanes};"]
    body: list[str] = []
    source = data.name
    if not data.vector:
        source = f"{inst}_d"
        sigs.append(f"signal {source} : {lanes};")
        body.append(f"{source}(0) <= {data.name};")
    body += [
        f"u_{inst}_ddr : entity work.mipi_ddr_in",
        f"\tgeneric map (width => {data.width})",
        f"\tport map (i_clk => {clk.name}, i_d => {source}, "
        f"o_q_early => {early}, o_q_late => {late});",
    ]
    return Wiring(
        [
            f"i_mipi_clk => {clk.name}",
            f"i_mipi_early => {early}",
            f"i_mipi_late => {late}",
        ],
        sigs,
        body,
    )


WIRING = {
    "wifi": _wifi,
    "mipi": _mipi,
    "ps2_keyboard": _ps2,
    "ps2_mouse_top": _ps2,
    "sd_spi": _sd_spi,
    "sd_native": _sd_native,
    "ir_receiver": _ir,
    "lcd": _lcd,
    "usb_bridge": _usb,
    "i2c_master": _i2c,
    "audio": _audio,
    "eth": _eth,
    "hdmi_tx": _hdmi,
    "hdmi_tmds_tx": _hdmi_tmds,
    "hdmi_audio": _hdmi_audio,
    "uart": _uart,
    "tv": _tv,
    "adc128s022": _adc128,
    "max10_adc_shell": _max10,
    "ltc2308": _ltc,
    "adxl345": _adxl,
    "spi": _spi,
    "video": _video,
}


def _hz(spec: TopSpec) -> int:
    """Dá a frequência do relógio do núcleo, em hertz."""
    core = spec.plan.get("core")
    return round(_HZ / float(core.period_ns)) if core else 50_000_000


def _literal(field_spec: FieldSpec, value: Any) -> str:
    """Escreve o valor de um campo como literal VHDL.

    Parameters
    ----------
    field_spec : FieldSpec
        O campo, cujo tipo diz a forma do literal.
    value : Any
        O valor lido da plataforma, já validado pelo tipo.

    Returns
    -------
    str
        `true` ou `false` para booleano, o número para inteiro, a cadeia
        entre aspas para `choice` e `hex`, e a cadeia de 7 bits para o
        endereço I2C.
    """
    if field_spec.type == "bool":
        return str(value).lower()
    if field_spec.type == "addr7":
        return f'"{int(value):07b}"'
    if field_spec.type in ("choice", "hex"):
        return f'"{value}"'
    return str(value)


def instance_generics(
    spec: TopSpec, item: dict[str, Any], variant: Variant, kind: Any
) -> list[str]:
    """Escreve os generics de uma entidade.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    item : dict of {str: Any}
        A entrada de `peripherals`.
    variant : Variant
        A entidade.
    kind : ExternalKind
        O kind, com os campos que viram generics.

    Returns
    -------
    list of str
        As associações: o relógio, os campos do kind e, no `spi`, o
        número de selecionadores.
    """
    out: list[str] = []
    if variant.clock_generic:
        out.append(f"{variant.clock_generic} => {_hz(spec)}")
    for field_spec in kind.fields:
        if field_spec.name not in item:
            continue
        value = item[field_spec.name]
        text = _literal(field_spec, value)
        out.append(f"{field_spec.generic} => {text}")
    if spec.video is not None and variant.entity == "video":
        out += spec.video.entity_generics()
    for name, at_base in _PS2_TABLES.get(variant.entity, {}).items():
        if name in item:
            continue
        out.append(f"{name} => {-(-at_base * _hz(spec) // _PS2_BASE_HZ)}")
    return out


def _bus_maps(variant: Variant, name: str, bits: int) -> list[str]:
    """Escreve a parte do `port map` que liga o barramento externo."""
    pos = f"{name.upper()}_EXT_POS"
    maps = [
        "i_clk => clk_core",
        "i_rst => soc_rst",
        f"i_write => ext_we({pos})",
        f"i_address => ext_addr({bits - 1} downto 0)",
        "i_data_in => ext_wdata",
        f"o_data_out => ext_rdata({_WORD} * {pos} + {_WORD - 1} downto "
        f"{_WORD} * {pos})",
    ]
    if variant.entity not in NO_READ:
        maps.append(f"i_read => ext_re({pos})")
    if variant.entity in WITH_PIXEL:
        maps.append("i_byteena => ext_byteena")
    return maps


def _wire(
    variant: Variant, item: dict[str, Any], pins: dict[str, Port]
) -> Wiring:
    """Liga uma entidade aos pinos, com o que o campo da entrada muda.

    Parameters
    ----------
    variant : Variant
        A entidade.
    item : dict of {str: Any}
        A entrada de `peripherals`.
    pins : dict of {str: Port}
        As portas da placa do periférico, por pino do papel.

    Returns
    -------
    Wiring
        As ligações; o `spi` fatia `cs_n` por `cs_count` e o RGMII lê
        `shifted_txc`.
    """
    inst = str(item["name"]).lower()
    if variant.entity == "spi":
        return _spi(inst, pins, int(item.get("cs_count", 1)))
    if variant.entity == "eth_rgmii_mac":
        shifted = bool(item.get("shifted_txc", True))
        return _eth_rgmii(inst, pins, shifted)
    return WIRING[variant.entity](inst, pins)


def _lanes_generic(item: dict[str, Any], width: int) -> list[str]:
    """Dá o generic `lanes` da câmera, que segue a largura do pino `d`.

    Parameters
    ----------
    item : dict of {str: Any}
        A entrada de `peripherals`.
    width : int
        Os bits do pino `d` da placa, um por lane.

    Returns
    -------
    list of str
        A associação, vazia quando a entrada já a escreveu (o gerador
        de generics a emitiu).

    Raises
    ------
    InputError
        Se `lanes` da entrada difere da largura do pino.
    """
    written = item.get("lanes")
    if written is None:
        return [f"lanes => {width}"]
    if int(written) != width:
        raise InputError(
            f"E peripheral {item['name']}: lanes {written} differs from "
            f"the {width} lanes of the board pin d"
        )
    return []


def _missing_clock(spec: TopSpec, variant: Variant) -> str:
    """Diz qual relógio de vídeo a entidade pede e o plano não tem.

    Parameters
    ----------
    spec : TopSpec
        O topo, com o plano de relógios.
    variant : Variant
        A entidade.

    Returns
    -------
    str
        `a pixel clock` ou `the serial clock (pixel_x5)`; vazio quando o
        plano tem o que a entidade pede.
    """
    if variant.entity in WITH_PIXEL and spec.plan.get("pixel") is None:
        return "a pixel clock"
    if variant.entity in SERIAL_ENTITIES and spec.plan.get("pixel_x5") is None:
        return "the serial clock (pixel_x5)"
    return ""


def _instance(
    spec: TopSpec,
    item: dict[str, Any],
    pins: dict[str, Port],
    notes: list[str],
) -> Wiring | None:
    """Escreve a instância de um periférico externo.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    item : dict of {str: Any}
        A entrada de `peripherals`.
    pins : dict of {str: Port}
        As portas da placa do periférico, por pino do papel.
    notes : list of str
        Recebe o aviso de quem fica fora.

    Returns
    -------
    Wiring or None
        As linhas; `None` quando o periférico fica fora.
    """
    name = str(item["name"])
    kind = EXTERNAL[str(item["kind"])]
    variant = kind.variant(item)
    if variant is None:
        return None
    pixel = spec.plan.get("pixel")
    missing = _missing_clock(spec, variant)
    if missing:
        notes.append(
            f"W peripheral {name}: {kind.name} needs {missing} and the "
            "clock plan has none; left out"
        )
        return None
    wired = _wire(variant, item, pins)
    generics = instance_generics(spec, item, variant, kind)
    if variant.entity == "mipi":
        generics += _lanes_generic(item, pins["d"].width)
    maps = _bus_maps(variant, name, variant.addr_bits) + wired.maps
    if kind.irq:
        maps.append(f"o_irq => ext_irq({name.upper()}_EXT_POS)")
    if pixel is not None and variant.entity in WITH_PIXEL:
        maps.append("i_pixel_clk => clk_pixel")
    if variant.entity in SERIAL_ENTITIES:
        maps.append("i_serial_clk => clk_pixel_x5")
    text = [
        f"\tu_{name.lower()} : entity work.{variant.entity}",
    ]
    if generics:
        text.append("\t\tgeneric map (" + ", ".join(generics) + ")")
    text.append(
        "\t\tport map (\n"
        + ",\n".join(f"\t\t\t{m}" for m in maps)
        + "\n\t\t);"
    )
    wired.body = [*text, *(f"\t{line}" for line in wired.body)]
    return wired


def external_top(spec: TopSpec) -> ExternalTop:
    """Monta o que os periféricos externos acrescentam ao topo.

    Parameters
    ----------
    spec : TopSpec
        O topo, com as portas que o `board_ports` montou.

    Returns
    -------
    ExternalTop
        Vazio sem periférico externo na plataforma.
    """
    gpios = board_gpio_list(spec.platform)
    items = external_list(spec.platform) + gpios
    result = ExternalTop()
    if not items:
        return result
    bits = max(
        (
            v.addr_bits
            for i in items
            if i.get("kind") != "gpio"
            and (v := EXTERNAL[str(i["kind"])].variant(i))
        ),
        default=1,
    )
    bits = max(bits, gpio_address_bits(spec, gpios))
    count = len(items)
    result.generics = [
        "ext_indices => EXT_INDICES",
        "ext_irq_ids => EXT_IRQ_IDS",
        f"ext_addr_width => {bits}",
    ]
    result.ports = [
        "o_ext_addr => ext_addr",
        "o_ext_wdata => ext_wdata",
        "o_ext_byteena => ext_byteena",
        "o_ext_we => ext_we",
        "o_ext_re => ext_re",
        "i_ext_rdata => ext_rdata",
        "i_ext_irq => ext_irq",
    ]
    result.signals = [
        "\t-- Periféricos externos: sinais.",
        f"\tsignal ext_addr : std_logic_vector({bits - 1} downto 0);",
        f"\tsignal ext_wdata : std_logic_vector({_WORD - 1} downto 0);",
        "\tsignal ext_byteena : std_logic_vector(3 downto 0);",
        f"\tsignal ext_we, ext_re, ext_irq : "
        f"std_logic_vector({count} - 1 downto 0);",
        "\tsignal ext_rdata : "
        f"std_logic_vector({_WORD * count - 1} downto 0);",
    ]
    result.body.append("\t-- Periféricos externos: instâncias.")
    for item in items:
        _place(spec, item, result)
    result.body.append("\t-- Periféricos externos: fim.")
    return result


def _place(spec: TopSpec, item: dict[str, Any], result: ExternalTop) -> None:
    """Instancia um periférico ou zera o que ele deixa no barramento."""
    name = str(item["name"])
    if item.get("kind") == "gpio":
        result.body += gpio_lines(spec, item)
        return
    pins = {p.pin: p for p in spec.ports if p.owner == name}
    variant = EXTERNAL[str(item["kind"])].variant(item)
    wired = None
    if variant is not None and variant.entity in MISSING_ENTITIES:
        raise InputError(
            f"E peripheral {name}: {item['kind']} cannot be generated, "
            f"{MISSING_ENTITIES[variant.entity]}"
        )
    if pins:
        wired = _instance(spec, item, pins, result.notes)
    if wired is None:
        pos = f"{name.upper()}_EXT_POS"
        result.body += [
            f"\text_rdata({_WORD} * {pos} + {_WORD - 1} downto "
            f"{_WORD} * {pos}) <= (others => '0');",
            f"\text_irq({pos}) <= '0';",
            "",
        ]
        return
    result.signals += [f"\t{s}" for s in wired.signals]
    result.body += [*wired.body, ""]
    if not EXTERNAL[str(item["kind"])].irq:
        result.body.append(f"\text_irq({name.upper()}_EXT_POS) <= '0';")
