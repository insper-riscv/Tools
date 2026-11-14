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

KIND_TIMER = "timer"
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
class FieldSpec:
    """A field of an entry of `peripherals`, written as a generic.

    Parameters
    ----------
    name : str
        The key of the entry.
    type : str
        `int` or `bool`.
    generic : str
        The generic of the entity that receives the value.
    group : str
        The part of the entity the field belongs to (`mac`, `mdio`),
        empty for a field with no part.
    """

    name: str
    type: str
    generic: str
    group: str = ""


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
        ),
        ExternalKind(
            "sd_native",
            "sd",
            True,
            _one("sd_native", 4, ">clk =cmd =dat", "clock_hz"),
        ),
        ExternalKind(
            "ir",
            "ir",
            True,
            _one("ir_receiver", 3, "<rxd", "clk_freq_hz"),
            fields=(FieldSpec("active_low", "bool", "active_low"),),
        ),
        ExternalKind(
            "lcd",
            "lcd",
            True,
            _one("lcd", 3, "=data >rs >rw >en >power >blon?", "clk_freq_hz"),
        ),
        ExternalKind(
            "usb",
            "usb",
            True,
            _one(
                "usb_bridge",
                4,
                ">addr =data >cs_n >rd_n >wr_n >rst_n <int",
            ),
            fields=(FieldSpec("int_active_high", "bool", "int_active_high"),),
        ),
        ExternalKind(
            "i2c",
            "i2c",
            True,
            _one("i2c_master", 3, "=scl =sda", "clk_freq"),
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
        ),
        ExternalKind(
            "eth",
            "eth",
            True,
            _one(
                "eth",
                6,
                "<rx_clk <rxd <rx_dv <rx_er <tx_clk >txd >tx_en >tx_er "
                ">mdc =mdio <int_n? >rst_n",
                "clk_freq_hz",
            ),
            fields=(
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
                "max10": Variant("max10_adc", 5, (), "clk_freq"),
            },
            "chip",
        ),
        ExternalKind(
            "spi",
            "spi",
            True,
            _one("spi", 3, ">sclk >mosi <miso >cs_n", "clock_hz"),
            fields=(FieldSpec("cs_count", "int", "cs_count"),),
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
            fields=(FieldSpec("three_wire", "bool", "three_wire"),),
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
