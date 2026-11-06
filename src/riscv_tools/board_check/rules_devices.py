"""The rules about the memory devices: V2, V3, V9, V10 and V19."""

from typing import Any

from riscv_tools.board_check.context import (
    BOARD_KEY,
    DEVICE_LABEL,
    DEVICE_OF,
    Context,
)
from riscv_tools.board_check.findings import Finding, error, size_text
from riscv_tools.memory_map.core import platform_dict
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.validation import hex_text

# As larguras de dado (bits) que o controlador de cada dispositivo liga.
BACKEND_WIDTHS = {"sdram": (16, 32), "sram": (16, 32), "nor": (8, 16)}
WORD_BITS = 32


def rule_v3(ctx: Context) -> list[Finding]:
    """Report a backend that asks for a device the board lacks.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        One error for each memory whose device the board does not carry.
    """
    provided = sorted(DEVICE_OF[key] for key in ctx.board.memories)
    listing = ", ".join(provided) or "none"
    return [
        error(
            "V3",
            f"memory.{key}.device {use.device} is not provided by board "
            f"'{ctx.board.board}' (provides: {listing}); "
            "use backend emulado",
        )
        for key, use in ctx.used_devices().items()
        if BOARD_KEY[str(use.device)] not in ctx.board.memories
    ]


def _provided_types(ctx: Context) -> set[str]:
    """List the resource types the board provides.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    set of str
        The keys of `memories`, plus `block_ram` and `vjtag` when the
        device has memory blocks and the family has the node.
    """
    found = set(ctx.board.memories)
    if ctx.board.resources.block_ram.total != 0:
        found.add("block_ram")
    if ctx.family.virtual_jtag and ctx.board.jtag.chain:
        found.add("vjtag")
    return found


def _missing_types(ctx: Context) -> list[str]:
    """List the needed types that neither V3 nor the board cover.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of str
        The types, sorted.
    """
    reported = {
        BOARD_KEY[str(use.device)] for use in ctx.used_devices().values()
    }
    return sorted(set(ctx.needs) - _provided_types(ctx) - reported)


def _sizes(ctx: Context, device: str) -> list[int]:
    """List the sizes of the regions a device realizes.

    Parameters
    ----------
    ctx : Context
        The platform against one board.
    device : str
        A device of the platform vocabulary.

    Returns
    -------
    list of int
        The bytes of each region whose memory uses the device.
    """
    used = ctx.used_devices()
    return [
        region.size
        for region in ctx.regions
        if region.memory in used and used[region.memory].device == device
    ]


def rule_v2(ctx: Context) -> list[Finding]:
    """Report a requirement of the platform that the board cannot meet.

    The requirements are the `needs` of the components of the top and
    the total bytes of the regions each device realizes. A region
    that is
    alone bigger than the device is V10's.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The errors.
    """
    name = ctx.fields.name
    board = ctx.board.board
    provided = sorted(_provided_types(ctx))
    listing = ", ".join(provided) or "none"
    found = [
        error(
            "V2",
            f"platform '{name}' requires {kind} but board '{board}' "
            f"provides: {listing}",
        )
        for kind in _missing_types(ctx)
    ]
    for device in ctx.used_devices().values():
        capacity = ctx.capacity(str(device.device))
        sizes = _sizes(ctx, str(device.device))
        if capacity is None or max(sizes, default=0) > capacity:
            continue
        if sum(sizes) > capacity:
            found.append(
                error(
                    "V2",
                    f"platform '{name}' requires {device.device} "
                    f"({size_text(sum(sizes))}) but board '{board}' "
                    f"provides {device.device} of {size_text(capacity)}",
                )
            )
    return found


def rule_v10(ctx: Context) -> list[Finding]:
    """Report a region bigger than the device behind it.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        One error for each region that does not fit.
    """
    used = ctx.used_devices()
    found: list[Finding] = []
    for region in ctx.regions:
        use = used.get(region.memory)
        capacity = None if use is None else ctx.capacity(str(use.device))
        if use is not None and capacity is not None and region.size > capacity:
            label = DEVICE_LABEL[str(use.device)]
            found.append(
                error(
                    "V10",
                    f"region {region.name} {size_text(region.size)} exceeds "
                    f"{label} capacity {size_text(capacity)} of board "
                    f"'{ctx.board.board}'",
                )
            )
    return found


def _sector(ctx: Context) -> tuple[int, str] | None:
    """Find the sector the FLASH banks must align to.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    tuple of (int, str) or None
        The sector and the words that name where it comes from; None
        when the FLASH has none.
    """
    rom = ctx.fields.memories.get("rom")
    if rom is None:
        return None
    if rom.backend == "dispositivo" and rom.device == "nor":
        chip = ctx.chip_of("nor")
        if chip is not None and chip.sector_bytes is not None:
            return chip.sector_bytes, f"NOR sector {{}} of chip {chip.chip}"
    if rom.backend == "emulado" and rom.sector_bytes is not None:
        return rom.sector_bytes, "emulated sector {} (memory.rom.sector_bytes)"
    return None


def rule_v9(ctx: Context) -> list[Finding]:
    """Report a FLASH bank that does not start on a sector.

    The offset counted is the one from the start of the FLASH region,
    which is the offset 0 of the chip.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        One error for each misaligned bank.
    """
    sector = _sector(ctx)
    flash = platform_dict(ctx.platform, "flash")
    if sector is None or not flash:
        return []
    size, where = sector
    start = {r.name: r.base for r in ctx.regions}.get(str(flash.get("region")))
    if start is None:
        return []
    found: list[Finding] = []
    banks: list[dict[str, Any]] = flash.get("banks") or []
    for bank in banks:
        offset = evaluate(bank["base"]) - start
        if offset % size:
            found.append(
                error(
                    "V9",
                    f"flash bank {bank['name']} base {hex_text(offset)} is "
                    f"not a multiple of the {where.format(hex_text(size))}",
                )
            )
    return found


def _widths(ctx: Context) -> dict[str, int]:
    """Give the data width each used device is wired with.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    dict of str to int
        The bits, keyed by device, for the devices that have a width.
    """
    found: dict[str, int] = {}
    for use in ctx.used_devices().values():
        device = str(use.device)
        memory = ctx.board.memories.get(BOARD_KEY[device])
        chip = ctx.chip_of(device)
        if memory is None or device not in BACKEND_WIDTHS:
            continue
        if device == "sdram" and chip is not None:
            found[device] = chip.width * memory.chips
        elif memory.bus_width is not None:
            found[device] = memory.bus_width
    return found


def rule_v19(ctx: Context) -> list[Finding]:
    """Report a bus width the backend of a device cannot slice.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        One error for each device wired with an unsupported width.
    """
    found: list[Finding] = []
    for device, width in _widths(ctx).items():
        supported = BACKEND_WIDTHS[device]
        if width in supported:
            continue
        listing = ", ".join(str(w) for w in supported)
        if width <= WORD_BITS and WORD_BITS % width == 0:
            need = f"needs {WORD_BITS // width} reads per word"
        else:
            need = f"does not divide the {WORD_BITS}-bit word"
        found.append(
            error(
                "V19",
                f"{device} bus_width {width} {need}; backend {device} "
                f"supports {listing}",
            )
        )
    return found
