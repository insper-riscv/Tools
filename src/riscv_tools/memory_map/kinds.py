"""The kinds of peripheral that `peripherals` accepts in `kind`.

A peripheral with no `kind` is a plain window (`base` and `size`). With
a `kind` it is one of these, and this is the only place that lists
them.

- `gpio` and `seg_display` take `base` and `groups`, never `size`: the
  window comes from the groups.
- `timer` takes `base` and `size`, which is at least 32 bytes.
- The external kinds (`EXTERNAL`) are the peripherals of the
  `Peripherals` repository that the generated top of a board
  instantiates next to the SoC: each one takes `base`, `size` (optional,
  at least the registers of the entity) and the fields of its entry
  here, and has the pins of a role of the board (`role`).
"""

from dataclasses import dataclass, field
from typing import Any

from riscv_tools.memory_map.kind_fields import (
    FieldSpec,
    bools,
    ints,
    ranged,
)

KIND_TIMER = "timer"
# Entidades com relógio de pixel (`i_pixel_clk`) e `i_byteena`.
PIXEL_ENTITIES = frozenset({"video", "hdmi_tx", "hdmi_tmds_tx"})
# Entidades que levam também o relógio serial de 5 vezes o do pixel.
SERIAL_ENTITIES = frozenset({"hdmi_tmds_tx"})
# Entidades que o `Peripherals` ainda não tem, com o motivo da recusa.
MISSING_ENTITIES = {
    "hdmi_tmds_tx": (
        "the serializer TMDS entity hdmi_tmds_tx is not in the "
        "Peripherals repository yet"
    )
}
GROUP_KINDS = ("gpio", "seg_display")
# A palavra de registrador, em bytes: a janela é 4 << bits do endereço.
WORD_BYTES = 4


@dataclass(frozen=True)
class BusPin:
    """One signal of a role of the board.

    Parameters
    ----------
    name : str
        The name in the role of `board.yaml` (`clk`, `dat`).
    direction : str
        `in`, `out` or `inout`, seen from the top of the board.
    required : bool
        Whether the role must name it.
    """

    name: str
    direction: str
    required: bool = True


@dataclass(frozen=True)
class Variant:
    """One entity of the `Peripherals` that a kind can stand for.

    Parameters
    ----------
    entity : str
        The entity the top instantiates.
    addr_bits : int
        The bits of the word address the entity takes.
    pins : tuple of BusPin
        The pins the entity needs on the board.
    clock_generic : str
        The generic that takes the clock of the core in hertz; empty
        when the entity has none.
    """

    entity: str
    addr_bits: int
    pins: tuple[BusPin, ...] = ()
    clock_generic: str = ""

    @property
    def window(self) -> int:
        """Give the bytes of registers of the entity.

        Returns
        -------
        int
            One word for each address the entity decodes.
        """
        return WORD_BYTES << self.addr_bits


@dataclass(frozen=True)
class ExternalKind:
    """A peripheral of the `Peripherals` that sits outside the SoC.

    Parameters
    ----------
    name : str
        The `kind` as written.
    role : str
        The role of the board whose pins it uses: a key of `buses` in
        `board.yaml`, or `video` for the video output.
    irq : bool
        Whether the entity has an interrupt line for the PLIC.
    variants : dict of {str: Variant}
        The entities, by the value of `variant_field`; the key is empty
        for a kind with one entity.
    variant_field : str
        The field that picks the entity (`device`, `chip`); empty when
        there is only one.
    default_variant : str
        The value taken when the field is not written; empty when the
        field is required.
    fields : tuple of FieldSpec
        The other fields the entry accepts.
    """

    name: str
    role: str
    irq: bool
    variants: dict[str, Variant]
    variant_field: str = ""
    default_variant: str = ""
    fields: tuple[FieldSpec, ...] = field(default_factory=tuple)

    def variant(self, item: dict[str, Any]) -> Variant | None:
        """Pick the entity of a peripheral.

        Parameters
        ----------
        item : dict of {str: Any}
            One entry of `peripherals`.

        Returns
        -------
        Variant or None
            The entity; None when `variant_field` is missing and has no
            default, or names none of the entities.
        """
        if not self.variant_field:
            return self.variants[""]
        key = str(item.get(self.variant_field, self.default_variant))
        return self.variants.get(key)


_IN = "in"
_OUT = "out"
_IO = "inout"


def _pins(spec: str) -> tuple[BusPin, ...]:
    """Write the pins of a role from a short text.

    Parameters
    ----------
    spec : str
        Names separated by spaces, each with a prefix for the direction
        (`>` out, `<` in, `=` inout) and a trailing `?` when optional.

    Returns
    -------
    tuple of BusPin
        The pins, in the order written.
    """
    way = {">": _OUT, "<": _IN, "=": _IO}
    out: list[BusPin] = []
    for word in spec.split():
        optional = word.endswith("?")
        name = word.lstrip("<>=").rstrip("?")
        out.append(BusPin(name, way[word[0]], not optional))
    return tuple(out)


def _one(
    entity: str, bits: int, pins: str, clock: str = ""
) -> dict[str, Variant]:
    """Make the table of a kind that has one entity.

    Parameters
    ----------
    entity : str
        The entity.
    bits : int
        The bits of its word address.
    pins : str
        The pins, as `_pins` reads them.
    clock : str
        The generic of the clock, if any.

    Returns
    -------
    dict of {str: Variant}
        The table, with the empty key.
    """
    return {"": Variant(entity, bits, _pins(pins), clock)}


EXTERNAL: dict[str, ExternalKind] = {
    kind.name: kind
    for kind in (
        ExternalKind(
            "ps2",
            "ps2",
            True,
            {
                "keyboard": Variant("ps2_keyboard", 2, _pins("=clk =dat")),
                "mouse": Variant("ps2_mouse_top", 3, _pins("=clk =dat")),
            },
            "device",
            "keyboard",
            fields=(
                *ints("rx_fifo_depth", 1, ("keyboard",)),
                *ints("filter_cycles inhibit_cycles timeout_cycles", 1),
                *ints(
                    "init_timeout_cycles packet_timeout_cycles",
                    1,
                    ("mouse",),
                ),
            ),
        ),
        ExternalKind(
            "video",
            "video",
            False,
            _one("video", 16, ""),
        ),
        ExternalKind(
            "sd_spi",
            "sd",
            True,
            _one("sd_spi", 3, ">clk =cmd =dat", "clock_hz"),
            fields=ints("init_sclk_hz rx_fifo_depth tx_fifo_depth", 1),
        ),
        ExternalKind(
            "sd_native",
            "sd",
            True,
            _one("sd_native", 4, ">clk =cmd =dat", "clock_hz"),
            fields=ints("init_clk_hz default_timeout input_sync_stages", 1),
        ),
        ExternalKind(
            "ir",
            "ir",
            True,
            _one("ir_receiver", 3, "<rxd", "clk_freq_hz"),
            fields=(
                *ints("tolerance_percent"),
                *ints("glitch_us timeout_us fifo_depth", 1),
                *bools("raw_enable active_low"),
            ),
        ),
        ExternalKind(
            "lcd",
            "lcd",
            True,
            _one("lcd", 3, "=data >rs >rw >en >power >blon?", "clk_freq_hz"),
            fields=(
                *ints("fifo_depth", 1),
                *bools("has_rw auto_init"),
                *ints(
                    "setup_ns pulse_ns hold_ns power_up_us exec_us "
                    "exec_long_us busy_timeout_us"
                ),
            ),
        ),
        ExternalKind(
            "usb",
            "usb",
            True,
            _one(
                "usb_bridge",
                4,
                ">addr =data >cs_n >rd_n >wr_n >rst_n <int <dreq? >dack?",
            ),
            fields=(
                *(
                    ranged(name, 0, 255)
                    for name in (
                        "setup_cycles",
                        "pulse_cycles",
                        "recovery_cycles",
                    )
                ),
                *bools("int_active_high"),
            ),
        ),
        ExternalKind(
            "i2c",
            "i2c",
            True,
            _one("i2c_master", 3, "=scl =sda", "clk_freq"),
            fields=ints("scl_freq", 1),
        ),
        ExternalKind(
            "audio",
            "audio",
            True,
            _one(
                "audio",
                4,
                ">xck >bclk >adclrck <adcdat >daclrck >dacdat",
                "clk_freq",
            ),
            # O generic `master` fica fora: a ligação do topo é a do
            # mestre, que dirige os três relógios do codec.
            fields=(
                *ints(
                    "xck_freq sample_rate slot_bits word_bits "
                    "tx_fifo_depth rx_fifo_depth tone_freq",
                    1,
                ),
                *ints("tone_amp"),
                *bools("has_tone autostart"),
            ),
        ),
        ExternalKind(
            "eth",
            "eth",
            True,
            {
                "mii": Variant(
                    "eth",
                    6,
                    _pins(
                        "<rx_clk <rxd <rx_dv <rx_er <tx_clk >txd >tx_en "
                        ">tx_er >mdc =mdio <int_n? >rst_n"
                    ),
                    "clk_freq_hz",
                ),
                # RGMII: TX_EN e RX_DV levam TX_CTL e RX_CTL (duas
                # bordas), e o relógio de envio sai por GTX_CLK.
                "rgmii": Variant(
                    "eth_rgmii_mac",
                    6,
                    _pins(
                        ">gtx_clk <rx_clk <rxd <rx_dv >txd >tx_en >mdc "
                        "=mdio <int_n? >rst_n"
                    ),
                    "clk_freq_hz",
                ),
            },
            "mode",
            "mii",
            fields=(
                FieldSpec(
                    "shifted_txc",
                    "bool",
                    "shifted_txc",
                    "mac",
                    only=("rgmii",),
                ),
                FieldSpec("phy_addr", "int", "phy_addr", "mdio"),
                FieldSpec("mdc_freq_hz", "int", "mdc_freq_hz", "mdio"),
                FieldSpec("poll_cycles", "int", "poll_cycles", "mdio"),
                FieldSpec(
                    "tx_buffer_addr_bits",
                    "int",
                    "tx_buffer_addr_bits",
                    "mac",
                ),
                FieldSpec(
                    "rx_buffer_addr_bits",
                    "int",
                    "rx_buffer_addr_bits",
                    "mac",
                ),
                FieldSpec(
                    "rx_fifo_addr_bits", "int", "rx_fifo_addr_bits", "mac"
                ),
                FieldSpec("sync_stages", "int", "sync_stages", "mac"),
                FieldSpec("reset_cycles", "int", "reset_cycles", "mac"),
            ),
        ),
        ExternalKind(
            "hdmi",
            "hdmi",
            True,
            _one(
                "hdmi_tx",
                16,
                ">d >clk >de >hs >vs <int =scl =sda",
                "clk_freq",
            ),
            fields=(
                *ints("fb_width fb_height scale", 1),
                FieldSpec(
                    "pixel_format",
                    "choice",
                    "pixel_format",
                    choices=("indexed", "direct"),
                ),
                *ints("h_visible h_sync v_visible v_sync", 1),
                *ints("h_front_porch h_back_porch v_front_porch v_back_porch"),
                *bools("h_sync_positive v_sync_positive"),
                *ints("mode_id pixel_clock_khz"),
                *bools("init_enable init_auto_start"),
                FieldSpec("init_table", "hex", "init_table"),
                FieldSpec("audio_init_table", "hex", "audio_init_table"),
                FieldSpec("i2c_dev_addr", "addr7", "i2c_dev_addr"),
                *ints("i2c_freq", 1),
                *bools("int_active_low"),
            ),
        ),
        ExternalKind(
            "hdmi_audio",
            "hdmi_audio",
            True,
            _one("hdmi_audio", 4, ">mclk >sclk >lrclk >i2s0", "clk_freq"),
            fields=(
                FieldSpec("sample_rate", "int", "sample_rate"),
                FieldSpec("mclk_ratio", "int", "mclk_ratio"),
                FieldSpec("word_bits", "int", "word_bits"),
                FieldSpec("tx_fifo_depth", "int", "tx_fifo_depth"),
                FieldSpec("has_tone", "bool", "has_tone"),
                FieldSpec("tone_freq", "int", "tone_freq"),
                FieldSpec("tone_amp", "int", "tone_amp"),
                FieldSpec("autostart", "bool", "autostart"),
            ),
        ),
        ExternalKind(
            "uart",
            "serial",
            True,
            _one("uart", 2, "<rx >tx <cts? >rts?"),
            fields=(
                FieldSpec("has_flow_control", "bool", "has_flow_control"),
                FieldSpec("baud_freq", "int", "baud_freq"),
                FieldSpec("baud_limit", "int", "baud_limit"),
                FieldSpec("rx_fifo_depth", "int", "rx_fifo_depth"),
                FieldSpec("tx_fifo_depth", "int", "tx_fifo_depth"),
            ),
        ),
        ExternalKind(
            "tv",
            "tv",
            True,
            _one("tv", 4, "<data <clk27 >reset_n"),
            fields=(
                *ints("fb_width fb_height src_width src_height", 1),
                *ints("present_cycles", 1),
                *bools("check_protection"),
            ),
        ),
        ExternalKind(
            "adc",
            "adc",
            True,
            {
                "adc128s022": Variant(
                    "adc128s022",
                    4,
                    _pins(">cs_n >sclk >saddr <sdat"),
                    "clock_hz",
                ),
                "ltc2308": Variant(
                    "ltc2308",
                    4,
                    _pins(">convst >sck >sdi <sdo"),
                    "clock_hz",
                ),
                "max10": Variant(
                    "max10_adc_shell", 5, _pins("<clk10"), "clk_freq"
                ),
            },
            "chip",
            fields=(
                *ints("sclk_hz", 1, ("adc128s022", "ltc2308")),
                FieldSpec(
                    "channel_latency",
                    "int",
                    "channel_latency",
                    maximum=1,
                    only=("adc128s022", "ltc2308"),
                ),
                *ints(
                    "convst_ns conversion_ns acquisition_ns", 1, ("ltc2308",)
                ),
                *ints("scan_freq", 1, ("max10",)),
            ),
        ),
        ExternalKind(
            "spi",
            "spi",
            True,
            _one("spi", 3, ">sclk >mosi <miso >cs_n", "clock_hz"),
            fields=(
                ranged("cs_count", 1, 64),
                ranged("word_width", 1, 32),
                *ints("reset_sclk_hz rx_fifo_depth tx_fifo_depth", 1),
            ),
        ),
        ExternalKind(
            "hdmi_tmds",
            "hdmi_tmds",
            False,
            _one("hdmi_tmds_tx", 16, ">tmds >clk =scl =sda <hpd?"),
        ),
        ExternalKind(
            "adxl345",
            "adxl345",
            True,
            _one(
                "adxl345",
                3,
                ">cs_n >sclk =mosi <miso? <int1?",
                "clock_hz",
            ),
            fields=(
                *ints("sclk_hz sample_hz cs_high_ns", 1),
                *bools("three_wire"),
            ),
        ),
    )
}
# Papéis de pino do `board.yaml` (seção `buses`), na ordem do registro.
BUS_ROLES = tuple(
    dict.fromkeys(k.role for k in EXTERNAL.values() if k.role != "video")
)
KINDS = (*GROUP_KINDS, KIND_TIMER, *EXTERNAL)


def is_group_block(item: dict[str, Any]) -> bool:
    """Tell whether a peripheral is a block of groups.

    Parameters
    ----------
    item : dict of {str: Any}
        One entry of `peripherals`.

    Returns
    -------
    bool
        True for `gpio` and `seg_display`.
    """
    return item.get("kind") in GROUP_KINDS


def external_of(item: dict[str, Any]) -> ExternalKind | None:
    """Give the external kind of a peripheral.

    Parameters
    ----------
    item : dict of {str: Any}
        One entry of `peripherals`.

    Returns
    -------
    ExternalKind or None
        The kind; None for any other peripheral.
    """
    return EXTERNAL.get(str(item.get("kind")))
