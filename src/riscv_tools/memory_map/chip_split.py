"""Split one memory chip between the FLASH and the RAM of a platform.

A chip (today the SDRAM) can hold the instruction segment and the data
segment at the same time. The platform says where each segment starts
inside the chip with `offset` (in bytes), so the split is whatever the
platform wants (32 MiB and 32 MiB, 16 MiB and 48 MiB, 48 MiB and 16
MiB, or any other), and nothing here fixes a size or a bit.

```yaml
memory:
  instructions:
    - {type: sdram, base: 0x00001000, size: 0x1FFF000, offset: 0x1000,
       on_bus: true}
  data:
    - {type: sdram, base: 0x40000000, size: 32M, offset: 32M,
       on_bus: true}
```

The core addresses a segment by its SoC address `A` in `[base, base +
size)`, and the chip by `offset + (A - base)`. The top turns the first
into the second without a subtraction whenever it can.

1. `low_bits` is the smallest `w` such that the segment does not cross
   a multiple of `2**w` in the SoC address, so the low `w` bits of `A`
   walk the segment.
2. When `offset - (base mod 2**w)` is a multiple of `2**w`, the bits of
   the chip address above `w` are a constant (`fixed_high`), and the
   address is the concatenation of that constant with the low `w` bits.
   This costs no logic.
3. Otherwise the chip address is the low `w` bits plus the constant
   `delta`, one adder of constant (`aligned` is false).

A segment without `offset` keeps the address of the SoC as it is, as
before.
"""

from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.memory_map.core import Mismatch, platform_dict, platform_list
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.layout import FLASH, RAM

# Dispositivo que aceita o campo `offset`.
OFFSET_DEVICE = "sdram"
# O deslocamento e o tamanho da região são múltiplos de uma página.
PAGE = 4096
_SIDES = (("rom", FLASH, "instructions"), ("ram", RAM, "data"))


@dataclass(frozen=True)
class ChipWindow:
    """Where one region sits inside its chip.

    Parameters
    ----------
    name : str
        The region (`FLASH` or `RAM`).
    base : int
        The first SoC address of the region.
    size : int
        The bytes of the region.
    offset : int
        The byte of the chip where the region starts.
    low_bits : int
        The width of the low part of the SoC address that walks the
        region.
    delta : int
        `offset - (base mod 2**low_bits)`, the constant that turns the
        low part of the SoC address into the chip address (negative
        when the region starts above its offset).
    """

    name: str
    base: int
    size: int
    offset: int
    low_bits: int
    delta: int

    @property
    def aligned(self) -> bool:
        """Say whether the chip address needs no adder.

        Returns
        -------
        bool
            True when `delta` is a non-negative multiple of
            `2**low_bits`.
        """
        return self.delta >= 0 and self.delta % (1 << self.low_bits) == 0

    @property
    def fixed_high(self) -> int:
        """Give the constant of the chip bits above the low bits.

        Returns
        -------
        int
            `delta >> low_bits` when `aligned`, 0 otherwise.
        """
        return self.delta >> self.low_bits if self.aligned else 0

    @property
    def end(self) -> int:
        """Give the first chip byte after the region.

        Returns
        -------
        int
            `offset + size`.
        """
        return self.offset + self.size


def low_bits(base: int, size: int) -> int:
    """Find the narrowest low part that walks a region without wrapping.

    Parameters
    ----------
    base : int
        The first SoC address.
    size : int
        The bytes.

    Returns
    -------
    int
        The smallest `w` with `(base mod 2**w) + size <= 2**w`.
    """
    bits = max(size - 1, 1).bit_length()
    while (base % (1 << bits)) + size > 1 << bits:
        bits += 1
    return bits


def _device(platform: dict[str, Any], key: str) -> str | None:
    """Read the device behind `rom` or `ram`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        `rom` or `ram`.

    Returns
    -------
    str or None
        The `device` of `memory.<key>`; None without one.
    """
    entry = platform_dict(platform, "memory").get(key)
    if not isinstance(entry, dict):
        return None
    device = cast("dict[str, Any]", entry).get("device")
    return None if device is None else str(device)


def _declared(
    platform: dict[str, Any],
) -> list[tuple[str, str, int, int, Any]]:
    """List the regions that write `offset`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of tuple
        For each region with an `offset`: the key (`rom` or `ram`), the
        region name, the base, the size and the raw offset.
    """
    regions = {str(r["name"]): r for r in platform_list(platform, "regions")}
    found: list[tuple[str, str, int, int, Any]] = []
    for key, name, _ in _SIDES:
        region = regions.get(name)
        if region is not None and "offset" in region:
            found.append(
                (
                    key,
                    name,
                    evaluate(region["base"]),
                    evaluate(region["size"]),
                    region["offset"],
                )
            )
    return found


def windows(platform: dict[str, Any]) -> dict[str, ChipWindow]:
    """Give the chip window of each region that writes `offset`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform, already checked by `problems`.

    Returns
    -------
    dict of {str: ChipWindow}
        Keyed by the region name (`FLASH`, `RAM`); a region without
        `offset` is not in it.
    """
    out: dict[str, ChipWindow] = {}
    for _, name, base, size, raw in _declared(platform):
        offset = evaluate(raw)
        low = low_bits(base, size)
        out[name] = ChipWindow(
            name, base, size, offset, low, offset - base % (1 << low)
        )
    return out


def _offset_problems(
    platform: dict[str, Any], key: str, name: str, size: int, raw: Any
) -> list[Mismatch]:
    """Check the `offset` of one region.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    key : str
        `rom` or `ram`.
    name : str
        The region.
    size : int
        The bytes of the region.
    raw : Any
        The offset as written.

    Returns
    -------
    list of Mismatch
        The problems of this offset alone.
    """
    where = f"memory {name}.offset"
    if _device(platform, key) != OFFSET_DEVICE:
        return [
            Mismatch("memory", "", f"{where} is only valid with type sdram")
        ]
    try:
        offset = evaluate(raw)
    except (ValueError, TypeError) as error:
        return [Mismatch("memory", "", f"{where} is not a number ({error})")]
    found: list[Mismatch] = []
    if offset < 0 or offset % PAGE or size % PAGE:
        found.append(
            Mismatch(
                "memory",
                "",
                f"{where} ({offset:#x}) and the size of {name} "
                f"({size:#x}) must be multiples of {PAGE} bytes",
            )
        )
    return found


def _sharing_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check two regions that sit in the same chip.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        A missing `offset` on one of the two regions and an overlap of
        the two ranges of the chip.
    """
    devices = [_device(platform, key) for key, _, _ in _SIDES]
    if devices != [OFFSET_DEVICE, OFFSET_DEVICE]:
        return []
    given = {name: raw for _, name, _, _, raw in _declared(platform)}
    missing = [name for _, name, _ in _SIDES if name not in given]
    if missing:
        return [
            Mismatch(
                "memory",
                "",
                f"{FLASH} and {RAM} share the sdram chip, so "
                f"{missing[0]} needs an offset (and so does the other)",
            )
        ]
    ranges = sorted(
        (w.offset, w.end, w.name) for w in windows(platform).values()
    )
    if ranges[0][1] > ranges[1][0]:
        return [
            Mismatch(
                "memory",
                "",
                f"{ranges[0][2]} [{ranges[0][0]:#x}, {ranges[0][1]:#x}) "
                f"overlaps {ranges[1][2]} [{ranges[1][0]:#x}, "
                f"{ranges[1][1]:#x}) in the chip",
            )
        ]
    return []


def problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the `offset` of the segments of a platform.

    The sum of the segments against the capacity of the chip is a rule
    of the board (V10 and V2), because only the board knows the chip.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        One per offset that is not valid and one per pair of regions
        that overlap or lack their offset.
    """
    found: list[Mismatch] = []
    for key, name, _, size, raw in _declared(platform):
        found += _offset_problems(platform, key, name, size, raw)
    return found or _sharing_problems(platform)
