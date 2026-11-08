"""O subcomando que gera o projeto Quartus de uma placa."""

import argparse
import sys
from pathlib import Path

from riscv_tools.board_equivalence import HandWritten, compare
from riscv_tools.board_generate import (
    Generated,
    ProjectRequest,
    build,
)
from riscv_tools.board_inputs import InputError
from riscv_tools.cli.common import project_root
from riscv_tools.pin_assignments import PinError
from riscv_tools.pll_generator import PllError
from riscv_tools.sdc_generator import SdcError
from riscv_tools.sources import SourcesError


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
    `--out/<platform>-<board>/` and, through the same code as
    `generate-memory-map`, the files of the memory map the platform
    asks for under `generate`; with `--check` it writes nothing and
    fails when a file on disk differs. With `--hand-qsf`, `--hand-sdc`
    and `--hand-pll` it also prints the equivalence report against the
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
    try:
        built = build(
            ProjectRequest(
                root=root,
                platform=args.platform,
                out=args.out,
                board=args.select_board,
                boards_dir=args.boards_dir,
                chips_dir=args.chips_dir,
                targets=tuple(args.target),
                seed=args.seed,
                accept_inferred=args.accept_inferred_pins,
                check=args.check,
            )
        )
    except (InputError, PinError, PllError, SdcError, SourcesError) as error:
        print(f"board generate: {error}", file=sys.stderr)
        sys.exit(2)
    for warning in built.generated.warnings:
        print(warning, file=sys.stderr)
    if built.problems:
        for problem in built.problems:
            print(f"board generate: {problem}", file=sys.stderr)
        sys.exit(1)
    if not args.check:
        print(f"project written to {built.folder}")
        for path in built.map_files:
            print(f"generated: {path.relative_to(root)}")
    if args.hand_qsf and not _compare(args, built.generated):
        sys.exit(1)
