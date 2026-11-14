"""Read the `buses` section: the pins of the external peripherals.

Each key of `buses` is a role of the registry of kinds
(`riscv_tools.memory_map.kinds`) and holds one mapping, or a list of
them when the board has several copies of the role (the two PS/2
channels of the DE0-CV). A mapping gives, for each pin of the role, the
signal of the pins file, which may be a bus:

```yaml
buses:
  ps2:
    - {clk: PS2_CLK, dat: PS2_DAT}
    - {clk: PS2_CLK2, dat: PS2_DAT2}
  sd: {clk: SD_CLK, cmd: SD_CMD, dat: "SD_DAT[3:0]"}
  adc: {chip: ltc2308, convst: ADC_CONVST, sck: ADC_SCK,
        sdi: ADC_SDI, sdo: ADC_SDO}
```

The pins a role needs depend on the entity (see `kinds.EXTERNAL`); a
pin that is not in the registry, or a missing required one, is a
problem of the file.
"""

from typing import Any, cast

from riscv_tools.board_schema.fields import Section
from riscv_tools.board_schema.model import BusInstance
from riscv_tools.board_schema.pins import expand_group
from riscv_tools.memory_map import kinds


def role_variants(role: str, chip: str = "") -> list[kinds.Variant]:
    """List the entities that can use one role of the board.

    Parameters
    ----------
    role : str
        The role (`sd`, `adc`).
    chip : str, optional
        The chip a copy of the role wires; limits the list when the
        role has one entity for each chip.

    Returns
    -------
    list of Variant
        The entities of every external kind of the role.
    """
    found: list[kinds.Variant] = []
    for kind in kinds.EXTERNAL.values():
        if kind.role != role:
            continue
        for key, variant in kind.variants.items():
            if kind.variant_field == "chip" and chip and key != chip:
                continue
            found.append(variant)
    return found


def role_pins(role: str, chip: str = "") -> dict[str, bool]:
    """List the pins a copy of a role may name.

    Parameters
    ----------
    role : str
        The role.
    chip : str, optional
        The chip, for the roles that have one.

    Returns
    -------
    dict of {str: bool}
        Each pin, and whether the copy must name it (required by every
        entity of the role).
    """
    pins: dict[str, bool] = {}
    for variant in role_variants(role, chip):
        for pin in variant.pins:
            pins[pin.name] = pins.get(pin.name, True) and pin.required
    return pins


def _chip_choices(role: str) -> tuple[str, ...]:
    """List the chips the registry knows for a role, empty if none."""
    return tuple(
        key
        for kind in kinds.EXTERNAL.values()
        if kind.role == role and kind.variant_field == "chip"
        for key in kind.variants
    )


def _instance(entry: Section, role: str) -> BusInstance:
    """Read one copy of a role.

    Parameters
    ----------
    entry : Section
        The mapping of the copy.
    role : str
        The role, which says the pins and the chips that are allowed.

    Returns
    -------
    BusInstance
        The copy; a problem is reported, not raised.
    """
    chips = _chip_choices(role)
    chip = entry.text("chip", required=bool(chips), choices=chips) or ""
    allowed = role_pins(role, chip)
    pins: list[tuple[str, str]] = []
    for pin, required in allowed.items():
        signal = entry.text(pin, required=required)
        if signal:
            pins.append((pin, signal))
    entry.done()
    return BusInstance(tuple(pins), chip)


def _role(section: Section, role: str) -> tuple[BusInstance, ...]:
    """Read the copies of one role.

    Parameters
    ----------
    section : Section
        The `buses` section.
    role : str
        The role.

    Returns
    -------
    tuple of BusInstance
        The copies, in order.
    """
    raw: Any = section.get(role)
    listed = cast("list[Any]", raw) if isinstance(raw, list) else [raw]
    return tuple(
        _instance(
            Section(f"{section.label}.{role}[{i}]", item, section.problems),
            role,
        )
        for i, item in enumerate(listed)
    )


def parse_buses(top: Section) -> dict[str, tuple[BusInstance, ...]]:
    """Read the `buses` section of a board.

    Parameters
    ----------
    top : Section
        The board.

    Returns
    -------
    dict of str to tuple of BusInstance
        The copies of each role; empty without the section.
    """
    section = top.section("buses", required=False)
    found: dict[str, tuple[BusInstance, ...]] = {}
    if section is None:
        return found
    for role in section.names():
        if role not in kinds.BUS_ROLES:
            section.fail(
                role, f"is not a bus role ({', '.join(kinds.BUS_ROLES)})"
            )
            continue
        found[role] = _role(section, role)
    return found


def bus_signals(instance: BusInstance) -> list[str]:
    """List the signals of the pins file that a copy cites.

    Parameters
    ----------
    instance : BusInstance
        The copy.

    Returns
    -------
    list of str
        The signals, bus after bus, as `expand_group` lists them.
    """
    return [name for _, spec in instance.pins for name in expand_group(spec)]
