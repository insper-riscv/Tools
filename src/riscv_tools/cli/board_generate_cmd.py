"""O subcomando que gera o projeto Quartus de uma placa."""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, cast

from riscv_tools import memory_map
from riscv_tools.board_equivalence import HandWritten, compare
from riscv_tools.board_generate import (
    Generated,
    GenerateRequest,
    check_project,
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


def _targets(args: argparse.Namespace, platform: Path) -> list[str]:
    """Escolhe os componentes cujo fecho de fontes entra no `.qsf`.

    Parameters
    ----------
    args : argparse.Namespace
        Uses args.target.
    platform : Path
        O `platform.yaml`, cujo campo `top` vale sem `--target`.

    Returns
    -------
    list of str
        Os `--target` dados ou, sem eles, o `top` da plataforma.
    """
    if args.target:
        return list(args.target)
    top: Any = memory_map.load_platform(platform).get("top") or []
    if isinstance(top, str):
        return [top]
    return [str(item) for item in cast("list[Any]", top)]


def _memory_map(root: Path, platform: Path, check: bool) -> list[str]:
    """Escreve ou confere os arquivos do mapa de memória da plataforma.

    É o mesmo caminho do `generate-memory-map`: o `board generate` não
    reimplementa o pacote do mapa, o linker nem os cabeçalhos.

    Parameters
    ----------
    root : Path
        A raiz do espaço de trabalho.
    platform : Path
        O `platform.yaml`.
    check : bool
        Verdadeiro compara com o disco em vez de escrever.

    Returns
    -------
    list of str
        Os problemas achados com `check`; vazio sem a seção `generate`.
    """
    if "generate" not in memory_map.load_platform(platform):
        return []
    if check:
        _, problems = memory_map.check_all(platform, root)
        return [str(problem) for problem in problems]
    for path in memory_map.write_all(platform, root):
        print(f"generated: {path.relative_to(root)}")
    return []


def _check_or_write(
    args: argparse.Namespace, root: Path, out: Path, result: Generated
) -> list[str]:
    """Escreve o projeto e o mapa, ou só os confere com `--check`.

    Parameters
    ----------
    args : argparse.Namespace
        Uses args.check and args.platform.
    root : Path
        A raiz do espaço de trabalho.
    out : Path
        A pasta de saída.
    result : Generated
        O projeto gerado.

    Returns
    -------
    list of str
        Os problemas da conferência; vazio ao escrever.
    """
    platform = root / args.platform
    if args.check:
        return check_project(out, result) + _memory_map(root, platform, True)
    folder = write_project(out, result)
    print(f"project written to {folder}")
    _memory_map(root, platform, False)
    return []


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
    out = root / args.out
    boards = root / (args.boards_dir or "boards")
    chips = root / (args.chips_dir or "Memory/chips")
    try:
        probe = generate(
            GenerateRequest(
                root / args.platform, args.select_board, boards, chips
            )
        )
        project = out / probe.folder
        result = generate(
            GenerateRequest(
                root / args.platform,
                args.select_board,
                boards,
                chips,
                _sources(root, _targets(args, root / args.platform), project),
                args.accept_inferred_pins,
                args.seed,
            )
        )
    except (InputError, PinError, PllError, SdcError, SourcesError) as error:
        print(f"board generate: {error}", file=sys.stderr)
        sys.exit(2)
    for warning in result.warnings:
        print(warning, file=sys.stderr)
    problems = _check_or_write(args, root, out, result)
    if problems:
        for problem in problems:
            print(f"board generate: {problem}", file=sys.stderr)
        sys.exit(1)
    if args.hand_qsf and not _compare(args, result):
        sys.exit(1)
