"""The rules about the console and the roles of I/O: V4, V5 and V6."""

from riscv_tools.board_check.context import Context
from riscv_tools.board_check.findings import Finding, error, warning
from riscv_tools.board_schema import IoNeed, IoRole, group_count


def rule_v4(ctx: Context) -> list[Finding]:
    """Report a console on pins when the board has no UART.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The error, when the platform asks for the console on pins.
    """
    if ctx.fields.console != "pinos" or ctx.board.console.uart:
        return []
    return [
        error(
            "V4",
            f"console pinos needs console.uart but board "
            f"'{ctx.board.board}' declares none; use console jtag",
        )
    ]


def _io_finding(
    role: str, need: IoNeed, have: IoRole | None, board: str
) -> Finding | None:
    """Judge one role the platform asks for against the board.

    Parameters
    ----------
    role : str
        The role.
    need : IoNeed
        What the platform wants.
    have : IoRole or None
        What the board has, None when it lacks the role.
    board : str
        The board name.

    Returns
    -------
    Finding or None
        The message, None when the board has enough units.
    """
    count = 0 if have is None else group_count(have.signals)
    if count >= need.count:
        return None
    shown = "none" if have is None else str(count)
    if need.need == "required":
        return error(
            "V5",
            f"io.{role} count {need.count} required but board '{board}' "
            f"has {shown}",
        )
    peripheral = role.upper()
    if have is None:
        return warning(
            "V6",
            f"io.{role} optional and not on board '{board}'; "
            f"the {peripheral} peripheral is omitted",
        )
    return warning(
        "V6",
        f"io.{role} count {need.count} optional but board '{board}' has "
        f"{count}; the {peripheral} peripheral is omitted",
    )


def rule_io(ctx: Context) -> list[Finding]:
    """Report the roles of I/O the board lacks, V5 and V6.

    A required role the board does not have, or has with fewer units, is
    an error. An optional one is a warning, because the peripheral is
    left out and its slot stays empty.

    Parameters
    ----------
    ctx : Context
        The platform against one board.

    Returns
    -------
    list of Finding
        The errors (V5) and the warnings (V6).
    """
    found = [
        _io_finding(role, need, ctx.board.io.get(role), ctx.board.board)
        for role, need in ctx.fields.io.items()
    ]
    return [finding for finding in found if finding is not None]
