"""The rules about what the board is: V16, V17 and V18."""

from riscv_tools.board_check.context import BOARD_KEY, Context
from riscv_tools.board_check.findings import Finding, error, warning
from riscv_tools.board_schema import (
    Board,
    bracketed,
    expand_group,
    role_signals,
)


def used_signals(ctx: Context) -> list[str]:
    """List the signals of the board the platform makes use of.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of str
        The reference clock, the reset, the groups of the roles the
        platform asks for and the console, as names of the pins file;
        the signals of the memories are the prefixes, listed apart.
    """
    board = ctx.board
    names: list[str] = [
        c.signal
        for c in board.clocks.inputs
        if c.name == board.clocks.reference
    ]
    names += expand_group(board.clocks.reset_signal)
    for role in ctx.fields.io:
        if role in board.io:
            names += role_signals(board.io[role])
    if ctx.fields.console == "pinos":
        names += list(board.console.uart)
    return names


def _used_prefixes(ctx: Context) -> list[str]:
    """List the prefixes of the signals of the devices in use.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of str
        The prefixes of the memories realized with a device.
    """
    found: list[str] = []
    for use in ctx.used_devices().values():
        memory = ctx.board.memories.get(BOARD_KEY[str(use.device)])
        if memory is not None:
            found += [f"{prefix}_" for prefix in memory.signals]
    return found


def rule_v16(ctx: Context) -> list[Finding]:
    """Report a pin that is only inferred and was not accepted.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        One error for each inferred pin in use.
    """
    if ctx.pins is None or ctx.accept_inferred_pins:
        return []
    names = set(used_signals(ctx))
    prefixes = tuple(_used_prefixes(ctx))
    return [
        error(
            "V16",
            f"pin {pin.pin} for {pin.name} is inferred, not confirmed; "
            "pass --accept-inferred-pins",
        )
        for pin in ctx.pins
        if pin.confirmed == "inferred"
        and (
            pin.name in names
            or bracketed(pin.name) in names
            or pin.name.startswith(prefixes)
        )
    ]


def rule_v18(ctx: Context) -> list[Finding]:
    """Warn of a family without calibration or a capacity not known.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The warnings.
    """
    found: list[Finding] = []
    if not ctx.calibrated:
        found.append(
            warning(
                "V18",
                f"family '{ctx.family.family}' has no calibration; "
                "capacity estimate skipped, only the fit decides",
            )
        )
    board = ctx.board
    capacities = {
        "logic": board.resources.logic.total,
        "block_ram": board.resources.block_ram.total,
        "multipliers": board.resources.multipliers.total,
        "plls": board.resources.plls,
    }
    found.extend(
        warning(
            "V18",
            f"board '{board.board}' has no capacity for {name}; "
            "its estimate is skipped, only the fit decides",
        )
        for name, total in capacities.items()
        if total is None
    )
    return found


def check_chain(
    board: Board, cable: str, observed: list[str]
) -> list[Finding]:
    """Compare the JTAG chain read from a cable with the board's.

    Parameters
    ----------
    board : Board
        The board the platform runs on.
    cable : str
        How the cable is named in the message (`[1-3]`).
    observed : list of str
        The IDCODEs of the chain, in order, in hexadecimal.

    Returns
    -------
    list of Finding
        The error (V17) when the chain is not the one the board expects.
    """
    expected = [device.idcode for device in board.jtag.chain]
    actual = [code.upper() for code in observed]
    if expected == actual:
        return []
    return [
        error(
            "V17",
            f"board '{board.board}' expects IDCODE {', '.join(expected)} "
            f"on cable {cable} but the chain has {', '.join(actual)}",
        )
    ]
