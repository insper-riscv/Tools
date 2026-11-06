"""Choose the board and the cable of a platform, by precedence.

From the strongest to the weakest source: `--cable`, `--board-id`,
`--board`, the `board:` of the platform, and `auto`. A weaker source
only fills what a stronger one left open. The key of a board is the
IDCODE of its chain plus the stable path of its USB port; neither the
cable name (it drifts) nor the USB serial number (it repeats between
cables) is used as a key.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from riscv_tools.board.errors import BoardBusyError, BoardError
from riscv_tools.board.inventory import Inventory
from riscv_tools.board.lock import is_free, read_owner
from riscv_tools.board.scan import (
    CableReport,
    PortResolver,
    chain_matches,
    scan,
)
from riscv_tools.board.spec import BoardSpec
from riscv_tools.jtag.hardware import Cable, ChainDevice, same_idcode

AUTO = "auto"


@dataclass(frozen=True)
class Request:
    """What the caller asked for.

    Attributes
    ----------
    cable : str or None
        `--cable`: the cable name, forced.
    board_id : str or None
        `--board-id`: an entry of the inventory.
    board : str or None
        `--board`: a board identifier.
    platform_board : str or None
        The `board:` of the platform, a board identifier or `auto`.
    allowed : tuple of str
        The `boards` list of the platform, the boards `auto` may take.
    free : bool
        Take the first free board among equal ones instead of failing
        with an ambiguity.
    """

    cable: str | None = None
    board_id: str | None = None
    board: str | None = None
    platform_board: str | None = None
    allowed: tuple[str, ...] = ()
    free: bool = False


@dataclass(frozen=True)
class Environment:
    """The host seen by the selection.

    Attributes
    ----------
    boards : dict of {str: BoardSpec}
        The known boards.
    inventory : Inventory
        The inventory of the host.
    cables : list of Cable
        The cables `jtagconfig` listed.
    resolve_port : callable
        Maps `<bus>-<port>` to the stable port path.
    lock_free : callable
        Tells whether a lock file is free.
    """

    boards: dict[str, BoardSpec]
    inventory: Inventory
    cables: list[Cable]
    resolve_port: PortResolver
    lock_free: Callable[[Path], bool] = is_free

    def reports(self) -> list[CableReport]:
        """Identify the cables of the host.

        Returns
        -------
        list of CableReport
            The scan of the host.
        """
        return scan(
            self.cables, self.boards, self.inventory, self.resolve_port
        )


@dataclass(frozen=True)
class Wire:
    """Where the FPGA of a board is reached.

    Attributes
    ----------
    cable : str
        The cable name for the `-c` of Quartus, valid for this session.
    fpga : ChainDevice
        The FPGA on the chain of the cable.
    port : str or None
        The stable path of the USB port.
    """

    cable: str
    fpga: ChainDevice
    port: str | None


@dataclass(frozen=True)
class Selection:
    """A board chosen, with what a program needs to use it.

    Attributes
    ----------
    board : str
        The board identifier.
    id : str
        The name of this physical board (inventory id, or
        `<board>-<host>`).
    wire : Wire
        The cable, the FPGA on it and the USB port.
    lock_file : Path
        The lock file of the board.
    warnings : tuple of str
        What the IDCODE does not prove, to be shown to the user.
    free : bool or None
        Whether the lock was free when checked; None when unchecked.
    """

    board: str
    id: str
    wire: Wire
    lock_file: Path
    warnings: tuple[str, ...] = field(default=())
    free: bool | None = None

    @property
    def cable(self) -> str:
        """Return the cable name for the `-c` of Quartus."""
        return self.wire.cable

    @property
    def device(self) -> str:
        """Return the Quartus identity of the FPGA on the cable.

        Returns
        -------
        str
            The `@1: 5CE(BA4|FA4) (0x02B050DD)` string.
        """
        return self.wire.fpga.identity

    @property
    def idcode(self) -> str:
        """Return the IDCODE of the FPGA."""
        return self.wire.fpga.idcode

    @property
    def port(self) -> str | None:
        """Return the stable path of the USB port."""
        return self.wire.port

    def as_dict(self) -> dict[str, Any]:
        """Return the selection as plain data for JSON.

        Returns
        -------
        dict of {str: Any}
            The fields, with the lock file as text.
        """
        return {
            "board": self.board,
            "id": self.id,
            "cable": self.cable,
            "device": self.device,
            "idcode": self.idcode,
            "port": self.port,
            "lock_file": str(self.lock_file),
            "warnings": list(self.warnings),
            "free": self.free,
        }


def _warnings(spec: BoardSpec, cable: Cable) -> tuple[str, ...]:
    """Say what the IDCODE does not prove (case 6 and case 4)."""
    fpga = spec.fpga
    for device in cable.devices:
        if same_idcode(device.idcode, fpga.idcode) and "/" in device.name:
            return (
                f"IDCODE {device.idcode} does not prove the variant: Quartus "
                f"names it {device.name} and {spec.board} declares "
                f"{spec.device or 'no device'}",
            )
    return ()


def _selection(env: Environment, report: CableReport, board: str) -> Selection:
    """Build the selection of one cable taken as a board."""
    spec = env.boards[board]
    fpga = spec.fpga
    device = next(
        d for d in report.cable.devices if same_idcode(d.idcode, fpga.idcode)
    )
    entry = report.entry
    host = env.inventory.host
    lock = env.inventory.lock_path(board, entry)
    return Selection(
        board,
        entry.id if entry else f"{board}-{host}",
        Wire(report.cable.name, device, report.port),
        lock,
        _warnings(spec, report.cable),
        env.lock_free(lock),
    )


def _searched(env: Environment, wanted: set[str] | None) -> str:
    """List the IDCODEs searched and the cables seen, for an error."""
    names = sorted(wanted if wanted is not None else env.boards)
    ids = sorted({env.boards[n].fpga.idcode for n in names if n in env.boards})
    seen = [c.name for c in env.cables] or ["no cable"]
    return f"searched IDCODEs {', '.join(ids)}; cables seen: {', '.join(seen)}"


def present(
    env: Environment, wanted: set[str] | None = None
) -> list[Selection]:
    """List the boards present on the host.

    Parameters
    ----------
    env : Environment
        The host.
    wanted : set of str, optional
        Keep only these boards; without it all known ones.

    Returns
    -------
    list of Selection
        One per (usable cable, board it may be), in port order.
    """
    return [
        _selection(env, report, board)
        for report in env.reports()
        if report.problem is None
        for board in report.boards
        if wanted is None or board in wanted
    ]


def _describe(options: list[Selection]) -> str:
    """List selections for an ambiguity error."""
    return "; ".join(
        f"{s.id} on {s.cable} at {s.port or 'unknown port'}" for s in options
    )


def _no_board(env: Environment, wanted: set[str] | None) -> BoardError:
    """Build the error of a request nothing answers."""
    problems = [r.problem for r in env.reports() if r.problem]
    detail = f" ({'; '.join(problems)})" if problems else ""
    case = 8 if any("case 8" in p for p in problems) else 7
    return BoardError(
        f"no board found: {_searched(env, wanted)}{detail}", case=case
    )


def _busy(options: list[Selection]) -> BoardBusyError:
    """Build the error of boards that are all in use."""
    parts: list[str] = []
    for option in options:
        owner = read_owner(option.lock_file)
        who = f"{owner.user}@{owner.host}: {owner.command}" if owner else "?"
        parts.append(f"{option.id} ({option.lock_file}) held by {who}")
    return BoardBusyError("every matching board is busy: " + "; ".join(parts))


def _pick(
    env: Environment,
    options: list[Selection],
    request: Request,
    wanted: set[str] | None,
) -> Selection:
    """Take the one board of the options, or say why none."""
    if not options:
        raise _no_board(env, wanted)
    if len(options) == 1:
        return options[0]
    free = [o for o in options if o.free]
    if request.free:
        if not free:
            raise _busy(options)
        return free[0]
    raise BoardError(
        f"{len(options)} boards match, pick one with --board-id or "
        f"--cable, or take the first free with --free: {_describe(options)}",
        case=2,
    )


def _forced_report(env: Environment, request: Request) -> CableReport:
    """Find the report of the cable that was forced."""
    for report in env.reports():
        if report.cable.name == request.cable:
            if report.cable.broken:
                raise BoardError(report.problem or "chain broken", case=8)
            return report
    names = ", ".join(c.name for c in env.cables) or "none"
    raise BoardError(
        f"cable {request.cable!r} not found; cables: {names}", case=7
    )


def _by_cable(env: Environment, request: Request) -> Selection:
    """Use the cable that was forced; the IDCODE is still checked."""
    report = _forced_report(env, request)
    expected = _expected_board(request)
    if expected is not None and expected not in env.boards:
        raise BoardError(f"unknown board {expected!r}")
    options = [expected] if expected else list(report.candidates)
    options = [
        b for b in options if chain_matches(env.boards[b], report.cable)
    ]
    if not options:
        raise BoardError(
            f"the chain of {request.cable} does not match "
            f"{expected or 'any known board'}: "
            f"{[d.idcode for d in report.cable.devices]}",
            case=7,
        )
    if len(options) > 1:
        raise BoardError(
            f"{request.cable} may be {', '.join(options)}; add --board",
            case=5,
        )
    return _selection(env, report, options[0])


def _expected_board(request: Request) -> str | None:
    """Name the board a weaker source asks for, if any.

    A forced cable dispenses with the inventory, so `--board-id` does
    not name a board here.
    """
    for name in (request.board, request.platform_board):
        if name and name != AUTO:
            return name
    return None


def _by_id(env: Environment, request: Request) -> Selection:
    """Use an entry of the inventory."""
    entry = env.inventory.by_id(request.board_id or "")
    if entry is None:
        known = ", ".join(e.id for e in env.inventory.entries) or "none"
        raise BoardError(
            f"board id {request.board_id!r} is not in the inventory; "
            f"known ids: {known}"
        )
    for report in env.reports():
        if report.port == entry.usb_path:
            if report.problem is not None:
                raise BoardError(report.problem)
            return _selection(env, report, entry.board)
    raise BoardError(
        f"{entry.id}: no cable at {entry.usb_path}; is the board plugged "
        "into its port and powered?"
    )


def _by_name(env: Environment, request: Request, name: str) -> Selection:
    """Use the board that was named; the IDCODE is checked."""
    if name not in env.boards:
        known = ", ".join(env.boards) or "none"
        raise BoardError(f"unknown board {name!r}; known boards: {known}")
    return _pick(env, present(env, {name}), request, {name})


def _by_auto(env: Environment, request: Request) -> Selection:
    """Resolve by JTAG among the boards present and free."""
    wanted = set(request.allowed) if request.allowed else None
    options = present(env, wanted)
    free = [o for o in options if o.free]
    if options and not free:
        raise _busy(options)
    return _pick(env, free, request, wanted)


def select_board(env: Environment, request: Request) -> Selection:
    """Choose the board and cable for a request.

    Parameters
    ----------
    env : Environment
        The host.
    request : Request
        The sources of the choice.

    Returns
    -------
    Selection
        The chosen board.

    Raises
    ------
    BoardError
        Nothing matches, or more than one does (the case numbers of
        the plan are on the error), or the chain is broken.
    BoardBusyError
        Every matching board is in use.
    """
    if request.cable:
        return _by_cable(env, request)
    if request.board_id:
        return _by_id(env, request)
    name = request.board or request.platform_board
    if name and name != AUTO:
        return _by_name(env, request, name)
    return _by_auto(env, request)
