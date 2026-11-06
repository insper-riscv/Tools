"""O subcomando que gera o projeto Quartus de uma placa."""

import argparse
import os
import sys
from pathlib import Path

from riscv_tools.board_equivalence import HandWritten, compare
from riscv_tools.board_generate import (
    Generated,
    GenerateRequest,
    generate,
    write_project,
)
from riscv_tools.board_inputs import InputError
from riscv_tools.cli.common import project_root
from riscv_tools.pin_assignments import PinError
from riscv_tools.pll_generator import PllError
from riscv_tools.sdc_generator import SdcError
from riscv_tools.sources import SourcesError, ordered_sources


def _sources(root: Path, targets: list[str], project: Path) -> tuple[str, ...]:
    """Resolve o fecho de fontes dos alvos para caminhos do projeto.

    Parameters
    ----------
    root : Path
        A raiz do espaço de trabalho.
    targets : list of str
        Os componentes.
    project : Path
        A pasta do projeto gerado.

    Returns
    -------
    tuple of str
        Os caminhos relativos à pasta do projeto.
    """
    if not targets:
        return ()
    return tuple(
        Path(os.path.relpath(root / path, project)).as_posix()
        for path in ordered_sources(root, targets)
    )


def _compare(args: argparse.Namespace, result: Generated) -> bool:
    """Imprime o relatório de equivalência contra os arquivos à mão.

    Parameters
    ----------
    args : argparse.Namespace
        Uses args.hand_qsf, args.hand_sdc and args.hand_pll.
    result : Generated
        O projeto gerado.

    Returns
    -------
    bool
        Verdadeiro quando o gerado cobre o escrito à mão.
    """
    pick = {
        suffix: next(t for n, t in result.files.items() if n.endswith(suffix))
        for suffix in (".qsf", ".sdc", "_pll.v")
    }
    hand = HandWritten(
        Path(args.hand_qsf).read_text(encoding="utf-8"),
        Path(args.hand_sdc).read_text(encoding="utf-8"),
        Path(args.hand_pll).read_text(encoding="utf-8"),
    )
    report = compare(
        hand,
        HandWritten(pick[".qsf"], pick[".sdc"], pick["_pll.v"]),
        renames={Path(args.hand_pll).stem: f"{result.name}_pll"},
        ignored_sources=frozenset(args.ignore_source),
    )
    print(report.render(), end="")
    return report.equivalent


def cmd_board_generate(args: argparse.Namespace) -> None:
    """Implement `riscv-tools board generate`.

    Writes the Quartus project of a platform on a board under
    `--out/<platform>-<board>/`; with `--hand-qsf`, `--hand-sdc` and
    `--hand-pll` it also prints the equivalence report against the
    hand-written files. Doesn't touch args.config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments of the `board generate` subcommand.

    Returns
    -------
    None
        Exits with status 2 when an input is invalid and with status 1
        when the equivalence report finds a difference.
    """
    root = project_root(args)
    out = root / args.out
    boards = root / (args.boards_dir or "boards")
    chips = root / (args.chips_dir or "Memory/chips")
    try:
        probe = generate(
            GenerateRequest(root / args.platform, args.board, boards, chips)
        )
        project = out / probe.folder
        result = generate(
            GenerateRequest(
                root / args.platform,
                args.board,
                boards,
                chips,
                _sources(root, args.target, project),
                args.accept_inferred_pins,
                args.seed,
            )
        )
    except (InputError, PinError, PllError, SdcError, SourcesError) as error:
        print(f"board generate: {error}", file=sys.stderr)
        sys.exit(2)
    for warning in result.warnings:
        print(warning, file=sys.stderr)
    folder = write_project(out, result)
    print(f"project written to {folder}")
    if args.hand_qsf and not _compare(args, result):
        sys.exit(1)
