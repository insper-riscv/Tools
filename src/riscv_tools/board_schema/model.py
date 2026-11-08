"""The typed records the board catalog files are read into."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PllSpec:
    """The PLL of a device family.

    Parameters
    ----------
    ip : str
        The IP that makes the PLL (`altera_pll` or `altpll`).
    vco_mhz : tuple of float
        The lowest and the highest frequency of the oscillator.
    clock_node_pattern : str
        The name of the internal clock nodes (for the constraints).
    outputs_max : int
        The outputs one PLL has.
    """

    ip: str
    vco_mhz: tuple[float, float]
    clock_node_pattern: str
    outputs_max: int


@dataclass(frozen=True)
class Family:
    """What holds for every device of a family.

    Parameters
    ----------
    family : str
        The identifier (`cyclone-v`).
    quartus_family : str
        The family as Quartus writes it (`Cyclone V`).
    logic_unit : str
        `alm` or `le`.
    pll : PllSpec
        The PLL of the family.
    block_ram_kind : str
        The kind of the memory block (`m10k`).
    block_ram_bits : int
        The bits of one memory block.
    memory_ip : str
        The IP that infers the memories.
    virtual_jtag : bool
        Whether the family has the Virtual JTAG node.
    onchip_flash : str or None
        The IP of the internal FLASH, None when the family has none.
    fmax_by_grade : dict of str to float or None
        The core frequency measured for each speed grade, in MHz; None
        for a grade that was not measured.
    calibration : str or None
        The calibration file, relative to the catalog of boards.
    slew_rate : bool
        Whether the family accepts the `SLEW_RATE` option on the
        3.3 V LVTTL pins (the MAX 10 fitter refuses it).
    qsf : tuple of str
        Assignments the `.qsf` of every project of the family carries
        (the MAX 10 needs its configuration mode for the memories that
        have an initial content).
    """

    family: str
    quartus_family: str
    logic_unit: str
    pll: PllSpec
    block_ram_kind: str
    block_ram_bits: int
    memory_ip: str
    virtual_jtag: bool
    onchip_flash: str | None
    fmax_by_grade: dict[str, float | None]
    calibration: str | None
    slew_rate: bool = True
    qsf: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chip:
    """A memory chip of the catalog, with its `extends` resolved.

    Parameters
    ----------
    chip : str
        The name.
    kind : str
        `sdram`, `sram` or `nor`.
    words : int
        The words of the chip.
    width : int
        The bits of one word.
    organization : dict of str to int
        Every field of the organization (banks and the address bits of
        the SDRAM included).
    timing : dict of str to float
        The timings, with the names of the datasheet.
    io_timing : dict of str to float
        The setup, hold and access times of the pins.
    max_mhz : float or None
        The clock ceiling of the speed grade.
    cas_latency : int or None
        The CAS latency of the SDRAM.
    sector_bytes : int or None
        The erase sector of the NOR.
    boot_sector_bytes : int or None
        The boot sector of the NOR.
    source : str
        `datasheet` or `inferido`.
    """

    chip: str
    kind: str
    words: int
    width: int
    organization: dict[str, int]
    timing: dict[str, float]
    io_timing: dict[str, float]
    max_mhz: float | None
    cas_latency: int | None
    sector_bytes: int | None
    boot_sector_bytes: int | None
    source: str

    @property
    def capacity_bytes(self) -> int:
        """Give the bytes one chip holds.

        Returns
        -------
        int
            Words times the width in bytes.
        """
        return self.words * self.width // 8


@dataclass(frozen=True)
class JtagDevice:
    """One device of the JTAG chain.

    Parameters
    ----------
    name : str
        The pattern `jtagconfig` prints for it.
    idcode : str
        The IDCODE, in hexadecimal.
    fpga : bool
        Whether it is the FPGA.
    hps : bool
        Whether it is the ARM hard processor system of the device.
    confirmed : str or None
        How the entry was learned (`manual`, `repo`, `inferred` or
        `measured`).
    """

    name: str
    idcode: str
    fpga: bool
    hps: bool = False
    confirmed: str | None = None


@dataclass(frozen=True)
class UsbId:
    """A USB identifier that tells the cable apart before a chain.

    Parameters
    ----------
    usb_id : str
        The `vid:pid` pair.
    state : str
        The state of the cable it stands for.
    confirmed : str
        How the entry was learned.
    """

    usb_id: str
    state: str
    confirmed: str


@dataclass(frozen=True)
class Capacity:
    """One capacity of the device, a count with the unit around it.

    Parameters
    ----------
    kind : str
        The unit or kind (`alm`, `m10k`, `dsp18x18`); empty for a bare
        count.
    total : int or None
        The elements the device has; None when it is not known.
    bits_per_block : int or None
        The bits of one block, for the memory blocks.
    """

    kind: str
    total: int | None
    bits_per_block: int | None = None


@dataclass(frozen=True)
class IoRole:
    """A role of the board's inputs and outputs.

    Parameters
    ----------
    signals : str
        The group of the pins file (`LEDR[9:0]`).
    active : str
        `high` or `low`.
    """

    signals: str
    active: str


@dataclass(frozen=True)
class MemoryDevice:
    """A memory the board carries, in the shape each kind needs.

    Parameters
    ----------
    chip : str or None
        The chip of the catalog; None for a memory inside the FPGA.
    chips : int
        The chips in parallel (the SDRAM); 1 for the others.
    bus_width : int or None
        The width wired, for the SRAM and the NOR.
    signals : tuple of str
        The prefixes of the signals in the pins file.
    clk_phase_ps : int or None
        The phase of the clock that leaves for the SDRAM.
    bytes : int or None
        The bytes, for the memories with no chip of the catalog.
    """

    chip: str | None = None
    chips: int = 1
    bus_width: int | None = None
    signals: tuple[str, ...] = ()
    clk_phase_ps: int | None = None
    bytes: int | None = None


@dataclass(frozen=True)
class ClockInput:
    """A clock that enters the board.

    Parameters
    ----------
    name : str
        The name the rest of the file uses.
    signal : str
        The signal of the pins file.
    mhz : float
        The frequency.
    """

    name: str
    signal: str
    mhz: float


@dataclass(frozen=True)
class Jtag:
    """The JTAG side of a board.

    Parameters
    ----------
    cable : str
        The kind of cable.
    cable_name : str or None
        The name `jtagconfig` gives the cable.
    chain : tuple of JtagDevice
        The devices expected in the chain, in order.
    usb : tuple of UsbId
        The USB identifiers of the cable.
    """

    cable: str
    cable_name: str | None
    chain: tuple[JtagDevice, ...]
    usb: tuple[UsbId, ...]


@dataclass(frozen=True)
class Resources:
    """What the device has, from `resources`.

    Parameters
    ----------
    logic : Capacity
        The logic of the device.
    block_ram : Capacity
        The memory blocks.
    multipliers : Capacity
        The multiplier elements.
    plls : int or None
        The PLLs.
    user_pins : int or None
        The user pins of the package.
    """

    logic: Capacity
    block_ram: Capacity
    multipliers: Capacity
    plls: int | None
    user_pins: int | None


@dataclass(frozen=True)
class Clocks:
    """The clocks and the reset of a board.

    Parameters
    ----------
    inputs : tuple of ClockInput
        The clocks that enter.
    reference : str
        The input that feeds the PLL.
    reset_signal : str
        The user reset signal.
    reset_active : str
        `high` or `low`.
    """

    inputs: tuple[ClockInput, ...]
    reference: str
    reset_signal: str
    reset_active: str


@dataclass(frozen=True)
class Console:
    """The console of a board.

    Parameters
    ----------
    default : str
        The default console, `jtag`.
    uart : tuple of str
        The receive and transmit signals of the UART, empty without one.
    """

    default: str
    uart: tuple[str, ...]


@dataclass(frozen=True)
class Board:
    """What a board offers, from its `board.yaml`.

    Parameters
    ----------
    board : str
        The identifier.
    name : str
        The commercial name.
    family : str
        The family file.
    device : str
        The complete device name.
    speed_grade : str
        The speed grade.
    target_level : str or None
        The support level aimed at, `N0` to `N4`.
    jtag : Jtag
        The cable and the chain.
    resources : Resources
        The capacities of the device.
    clocks : Clocks
        The clocks and the reset.
    io : dict of str to IoRole
        The roles of inputs and outputs.
    memories : dict of str to MemoryDevice
        The memories, keyed `sdram`, `sram`, `nor`, `onchip_flash`,
        `serial_flash`.
    console : Console
        The default console and the UART.
    pins : str
        The pins file, relative to the board folder.
    notes : tuple of str
        The traps of the board.
    """

    board: str
    name: str
    family: str
    device: str
    speed_grade: str
    target_level: str | None
    jtag: Jtag
    resources: Resources
    clocks: Clocks
    io: dict[str, IoRole]
    memories: dict[str, MemoryDevice]
    console: Console
    pins: str = "pins.yaml"
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Pin:
    """One signal of a pins file.

    Parameters
    ----------
    name : str
        The signal, with the index in brackets for a bus.
    pin : str
        The pin of the device.
    io_standard : str
        The I/O standard of Quartus.
    direction : str
        `in`, `out` or `inout`.
    confirmed : str
        `manual`, `repo` or `inferred`.
    """

    name: str
    pin: str
    io_standard: str
    direction: str
    confirmed: str
