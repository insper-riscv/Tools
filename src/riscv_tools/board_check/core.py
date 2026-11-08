"""Run the provides and requires rules on a platform and its boards.

The rules run in `check-memory-map`, on every board the platform names.
A platform that names no board (`board` or `boards`) is not checked, so
the platforms written before the board catalog keep passing.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from riscv_tools.board_check.context import Context, external_regions
from riscv_tools.board_check.findings import Finding, error
from riscv_tools.board_check.rules_board import (
    rule_v16,
    rule_v18,
)
from riscv_tools.board_check.rules_clocks import rule_v7, rule_v8, rule_v15
from riscv_tools.board_check.rules_devices import (
    rule_v2,
    rule_v3,
    rule_v9,
    rule_v10,
    rule_v19,
)
from riscv_tools.board_check.rules_fit import capacity_report, rule_fit
from riscv_tools.board_check.rules_roles import rule_io, rule_v4
from riscv_tools.board_schema import (
    Board,
    Catalog,
    Chip,
    Family,
    NotFoundError,
    Pin,
    PlatformBoardFields,
    SchemaError,
    declares_board,
    parse_platform_fields,
)
from riscv_tools.board_schema.platform_fields import read_platform_file
from riscv_tools.fit_estimate.table import CalibrationTable, load_table
from riscv_tools.sources import SourcesError, closure_needs

RULES = (
    rule_v2,
    rule_v3,
    rule_v4,
    rule_io,
    rule_v7,
    rule_v8,
    rule_v9,
    rule_v10,
    rule_v15,
    rule_v16,
    rule_v18,
    rule_v19,
    rule_fit,
)
KNOWN_SHOWN = 12


def _known(names: list[str]) -> str:
    """Write the names the catalog has, for a not-found message.

    Parameters
    ----------
    names : list of str
        The names.

    Returns
    -------
    str
        The first names, with `...` when there are more.
    """
    shown = ", ".join(names[:KNOWN_SHOWN])
    return shown + (", ..." if len(names) > KNOWN_SHOWN else "")


def _chips(
    catalog: Catalog, board_name: str, names: list[str]
) -> tuple[dict[str, Chip], list[Finding]]:
    """Read the chips a board carries.

    Parameters
    ----------
    catalog : Catalog
        The catalog.
    board_name : str
        The board, for the messages.
    names : list of str
        The chips the board names.

    Returns
    -------
    tuple of (dict of str to Chip, list of Finding)
        The chips read and one V1 error for each one that failed.
    """
    chips: dict[str, Chip] = {}
    found: list[Finding] = []
    for name in names:
        try:
            chips[name] = catalog.load_chip(name)
        except NotFoundError as missing:
            found.append(
                error(
                    "V1",
                    f"chip '{name}' of board '{board_name}' not found in "
                    f"chips/ (known: {_known(missing.known)})",
                )
            )
        except SchemaError as bad:
            found.extend(
                error("V1", f"chip '{name}' is invalid: {problem}")
                for problem in bad.problems
            )
    return chips, found


def _pins(
    catalog: Catalog, board_name: str, board: Board
) -> tuple[list[Pin] | None, list[Finding]]:
    """Read the pins file of a board.

    Parameters
    ----------
    catalog : Catalog
        The catalog.
    board_name : str
        The board.
    board : Board
        The board, which names its pins file.

    Returns
    -------
    tuple of (list of Pin or None, list of Finding)
        The signals, None when the file cannot be read, and the V1
        errors.
    """
    try:
        return catalog.load_pins(board_name, board), []
    except SchemaError as bad:
        return None, [
            error("V1", f"pins of board '{board_name}': {problem}")
            for problem in bad.problems
        ]


def _calibrated(catalog: Catalog, family: Family) -> bool:
    """Tell whether the family has its calibration file.

    Parameters
    ----------
    catalog : Catalog
        The catalog.
    family : Family
        The family.

    Returns
    -------
    bool
        True when the family names a calibration file that exists.
    """
    return bool(
        family.calibration and (catalog.boards / family.calibration).is_file()
    )


def _table(
    catalog: Catalog, family: Family
) -> tuple[CalibrationTable | None, list[Finding]]:
    """Read the calibration table of the family.

    Parameters
    ----------
    catalog : Catalog
        The catalog.
    family : Family
        The family.

    Returns
    -------
    tuple of (CalibrationTable or None, list of Finding)
        The table, None when the family names no file, it is absent or
        it is invalid, and the V1 error of an invalid one.
    """
    if not _calibrated(catalog, family):
        return None, []
    path = catalog.boards / str(family.calibration)
    try:
        return load_table(path), []
    except (ValueError, yaml.YAMLError) as bad:
        return None, [
            error("V1", f"calibration of family '{family.family}': {bad}")
        ]


def _not_found(missing: NotFoundError, board_name: str) -> Finding:
    """Word the error of a board or a family the catalog lacks.

    Parameters
    ----------
    missing : NotFoundError
        What was not found.
    board_name : str
        The board being read.

    Returns
    -------
    Finding
        The V1 error.
    """
    where = "boards/" if missing.kind == "board" else "boards/families/"
    owner = "" if missing.kind == "board" else f" of board '{board_name}'"
    return error(
        "V1",
        f"{missing.kind} '{missing.name}'{owner} not found in "
        f"{where} (known: {_known(missing.known)})",
    )


def _context(
    platform: dict[str, Any],
    fields: PlatformBoardFields,
    board_name: str,
    catalog: Catalog,
    accept_inferred_pins: bool,
) -> tuple[Context | None, list[Finding]]:
    """Read a board and what it names, ready for the rules.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    fields : PlatformBoardFields
        Its board fields.
    board_name : str
        The board to read.
    catalog : Catalog
        The catalog.
    accept_inferred_pins : bool
        Whether a pin only inferred may be used.

    Returns
    -------
    tuple of (Context or None, list of Finding)
        The context, None when the board or its family cannot be read,
        and the V1 errors.
    """
    try:
        board = catalog.load_board(board_name)
        family = catalog.load_family(board.family)
    except NotFoundError as missing:
        return None, [_not_found(missing, board_name)]
    except SchemaError as bad:
        return None, [
            error("V1", f"board '{board_name}' is invalid: {problem}")
            for problem in bad.problems
        ]
    chips, found = _chips(
        catalog,
        board_name,
        [m.chip for m in board.memories.values() if m.chip],
    )
    pins, problems = _pins(catalog, board_name, board)
    table, bad_table = _table(catalog, family)
    ctx = Context(
        platform,
        fields,
        board,
        family,
        chips,
        (),
        pins,
        _calibrated(catalog, family),
        accept_inferred_pins,
        external_regions(platform),
        table,
    )
    return ctx, found + problems + bad_table


def _needs(
    root: Path, fields: PlatformBoardFields
) -> tuple[tuple[str, ...], list[Finding]]:
    """Collect the `needs` of the closure of the top of the platform.

    Parameters
    ----------
    root : Path
        The workspace root, whose `paths.yaml` files are read.
    fields : PlatformBoardFields
        The board fields, which name the top.

    Returns
    -------
    tuple of (tuple of str, list of Finding)
        The resource types, and a V2 error when the top cannot be
        resolved.
    """
    if not fields.top:
        return (), []
    try:
        return tuple(closure_needs(root, list(fields.top))), []
    except SourcesError as bad:
        return (), [error("V2", f"top cannot be resolved: {bad}")]


def check_platform(
    platform: dict[str, Any],
    root: Path,
    *,
    accept_inferred_pins: bool = False,
    catalog: Catalog | None = None,
) -> list[Finding]:
    """Check a loaded platform against the boards it names.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    root : Path
        The project root, where the catalog and the manifests are.
    accept_inferred_pins : bool, optional
        Whether a pin only inferred may be used.
    catalog : Catalog, optional
        The catalog; by default the one found from the root.

    Returns
    -------
    list of Finding
        Errors and warnings, board by board; empty for a platform that
        names no board.
    """
    if not declares_board(platform):
        return []
    try:
        fields = parse_platform_fields(platform)
    except SchemaError as bad:
        return [error("schema", f"platform {p}") for p in bad.problems]
    found_catalog = catalog or Catalog.for_root(root)
    needs, found = _needs(root, fields)
    for name in fields.candidates():
        ctx, problems = _context(
            platform, fields, name, found_catalog, accept_inferred_pins
        )
        found += problems
        if ctx is None:
            continue
        ctx = replace(ctx, needs=needs)
        for rule in RULES:
            found += rule(ctx)
    return found


def check_platform_file(
    path: Path,
    root: Path,
    *,
    accept_inferred_pins: bool = False,
) -> list[Finding]:
    """Read a platform file with its `extends` chain and check it.

    Parameters
    ----------
    path : Path
        The platform YAML.
    root : Path
        The project root.
    accept_inferred_pins : bool, optional
        Whether a pin only inferred may be used.

    Returns
    -------
    list of Finding
        The errors and warnings.
    """
    return check_platform(
        read_platform_file(path),
        root,
        accept_inferred_pins=accept_inferred_pins,
    )


def fit_report(
    platform: dict[str, Any], board_name: str, catalog: Catalog
) -> tuple[dict[str, Any] | None, list[Finding]]:
    """Estimate the fit of a platform on one board.

    Parameters
    ----------
    platform : dict of str to Any
        The loaded platform.
    board_name : str
        The board.
    catalog : Catalog
        The catalog.

    Returns
    -------
    tuple of (dict or None, list of Finding)
        The report of `capacity.json`, None when the family has no
        calibration, and the findings of the fit (V11 to V13, V18).
    """
    try:
        fields = parse_platform_fields(platform)
    except SchemaError as bad:
        return None, [error("schema", f"platform {p}") for p in bad.problems]
    ctx, found = _context(platform, fields, board_name, catalog, True)
    if ctx is None:
        return None, found
    return capacity_report(ctx), rule_fit(ctx)
