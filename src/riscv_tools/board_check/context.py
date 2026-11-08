"""What the rules compare: the platform, one board and its catalog."""

from dataclasses import dataclass, field
from typing import Any

from riscv_tools.board_schema import (
    Board,
    Chip,
    Family,
    Pin,
    PlatformBoardFields,
)
from riscv_tools.board_schema.platform_fields import MemoryUse
from riscv_tools.fit_estimate.table import CalibrationTable
from riscv_tools.memory_map.core import platform_list
from riscv_tools.memory_map.expressions import evaluate

# A chave de `memories` do board.yaml para cada dispositivo do platform.
BOARD_KEY = {
    "sdram": "sdram",
    "sram": "sram",
    "nor": "nor",
    "flash-interna": "onchip_flash",
    "serial": "serial_flash",
}
DEVICE_OF = {key: device for device, key in BOARD_KEY.items()}
DEVICE_LABEL = {
    "sdram": "SDRAM",
    "sram": "SRAM",
    "nor": "NOR",
    "flash-interna": "internal FLASH",
    "serial": "serial FLASH",
}


@dataclass(frozen=True)
class Region:
    """A region behind the external port of the core.

    Parameters
    ----------
    name : str
        The region name.
    base : int
        The first address.
    size : int
        The bytes.
    memory : str
        `rom` or `ram`.
    """

    name: str
    base: int
    size: int
    memory: str


@dataclass(frozen=True)
class Context:
    """A platform against one board.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform, for the map.
    fields : PlatformBoardFields
        The board fields of the platform.
    board : Board
        The board.
    family : Family
        The family of the board.
    chips : dict of str to Chip
        The chips the board carries, keyed by name.
    needs : tuple of str
        The board resource types the closure of the top needs.
    pins : list of Pin or None
        The signals of the board; None when the file was not read.
    calibrated : bool
        Whether the calibration file of the family exists.
    accept_inferred_pins : bool
        Whether a pin that is only inferred may be used.
    regions : list of Region
        The regions behind the external memories.
    table : CalibrationTable or None
        The calibration table of the family; None without the file.
    """

    platform: dict[str, Any]
    fields: PlatformBoardFields
    board: Board
    family: Family
    chips: dict[str, Chip]
    needs: tuple[str, ...] = ()
    pins: list[Pin] | None = None
    calibrated: bool = False
    accept_inferred_pins: bool = False
    regions: list[Region] = field(default_factory=list[Region])
    table: CalibrationTable | None = None

    def used_devices(self) -> dict[str, MemoryUse]:
        """List the memories the platform realizes with a device.

        Returns
        -------
        dict of str to MemoryUse
            `rom` and `ram` whose backend is `dispositivo`.
        """
        return {
            key: use
            for key, use in self.fields.memories.items()
            if use.backend == "dispositivo" and use.device is not None
        }

    def chip_of(self, device: str) -> Chip | None:
        """Find the chip of a kind of device on the board.

        Parameters
        ----------
        device : str
            A device of the platform vocabulary.

        Returns
        -------
        Chip or None
            The chip; None when the board lacks the memory or it has
            none in the catalog.
        """
        memory = self.board.memories.get(BOARD_KEY[device])
        return None if memory is None else self.chips.get(memory.chip or "")

    def capacity(self, device: str) -> int | None:
        """Give the bytes the board has of one kind of device.

        Parameters
        ----------
        device : str
            A device of the platform vocabulary.

        Returns
        -------
        int or None
            The bytes; None when the board lacks the device or the size
            is not known.
        """
        memory = self.board.memories.get(BOARD_KEY[device])
        if memory is None:
            return None
        if memory.bytes is not None:
            return memory.bytes
        chip = self.chip_of(device)
        return None if chip is None else chip.capacity_bytes * memory.chips


def external_regions(platform: dict[str, Any]) -> list[Region]:
    """List the regions that sit behind the external memories.

    The first region of a platform is the boot memory, which is always
    inside the core; the others are the ROM or the RAM by their `kind`.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.

    Returns
    -------
    list of Region
        The regions after the boot memory.
    """
    return [
        Region(
            str(item["name"]),
            evaluate(item["base"]),
            evaluate(item["size"]),
            "ram" if item.get("kind") == "ram" else "rom",
        )
        for item in platform_list(platform, "regions")[1:]
    ]
