"""Escreve o projeto de uma plataforma e os arquivos do mapa de memória.

É o caminho único da geração: o `board generate`, o `program` e o
orquestrador de testes na placa chamam `build`, que escreve (ou, com
`check`, só confere) o projeto do Quartus e chama o mesmo código do
`generate-memory-map` para o pacote do mapa, o linker e os cabeçalhos.
"""

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from riscv_tools import board_check, memory_map
from riscv_tools.board_generate.core import (
    Generated,
    GenerateRequest,
    check_project,
    generate,
    write_project,
)
from riscv_tools.board_inputs import InputError, resolve_board_name
from riscv_tools.board_schema import Catalog
from riscv_tools.board_schema.platform_fields import read_platform_file
from riscv_tools.sources import ordered_sources


@dataclass(frozen=True)
class ProjectRequest:
    """O pedido de um projeto.

    Attributes
    ----------
    root : Path
        A raiz do espaço de trabalho.
    platform : str
        O `platform.yaml`, relativo à raiz.
    out : str
        A pasta de saída, relativa à raiz.
    board : str or None
        A placa; `None` usa a da plataforma.
    boards_dir : str or None
        A pasta `boards/`; `None` é `boards`.
    chips_dir : str or None
        O catálogo de chips; `None` é `Memory/chips`.
    targets : tuple of str
        Componentes do `.qsf`; vazio usa o campo `top` da plataforma.
    seed : int
        Semente do `.qsf`.
    accept_inferred : bool
        Aceita construir com pino `inferred`.
    check : bool
        Só confere o disco, sem escrever.
    """

    root: Path
    platform: str
    out: str
    board: str | None = None
    boards_dir: str | None = None
    chips_dir: str | None = None
    targets: tuple[str, ...] = ()
    seed: int = 5
    accept_inferred: bool = False
    check: bool = False


@dataclass(frozen=True)
class ProjectResult:
    """O que `build` fez.

    Attributes
    ----------
    generated : Generated
        O projeto gerado.
    folder : Path
        A pasta do projeto.
    problems : list of str
        Arquivos ausentes ou desatualizados, só com `check`.
    map_files : list of Path
        Arquivos do mapa escritos, só sem `check`.
    """

    generated: Generated
    folder: Path
    problems: list[str] = field(default_factory=list[str])
    map_files: list[Path] = field(default_factory=list[Path])


def sources_of(
    root: Path, targets: list[str], project: Path
) -> tuple[str, ...]:
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


def repository_root(platform: Path, fallback: Path) -> Path:
    """Acha o clone do repositório que contém a plataforma.

    Num projeto consumidor (Tests, Certification) o repositório da
    plataforma é um submódulo, e os repositórios que os componentes
    pedem (Common-Components, Memory e os outros) são submódulos dele, e
    não da raiz do consumidor. A lista de fontes parte, por isso, da
    pasta que tem o `paths.yaml` da plataforma.

    Parameters
    ----------
    platform : Path
        O `platform.yaml`.
    fallback : Path
        A raiz do espaço de trabalho, quando nenhuma pasta acima da
        plataforma tem `paths.yaml`.

    Returns
    -------
    Path
        A pasta mais próxima acima da plataforma com `paths.yaml`.
    """
    for folder in platform.parents:
        if (folder / "paths.yaml").is_file():
            return folder
    return fallback


def targets_of(platform: Path, given: tuple[str, ...]) -> list[str]:
    """Escolhe os componentes cujo fecho de fontes entra no `.qsf`.

    Parameters
    ----------
    platform : Path
        O `platform.yaml`, cujo campo `top` vale sem alvos dados.
    given : tuple of str
        Os alvos pedidos.

    Returns
    -------
    list of str
        Os alvos dados ou, sem eles, o `top` da plataforma.
    """
    if given:
        return list(given)
    top: Any = memory_map.load_platform(platform).get("top") or []
    if isinstance(top, str):
        return [top]
    return [str(item) for item in cast("list[Any]", top)]


def _memory_map(
    root: Path, platform: Path, check: bool
) -> tuple[list[str], list[Path]]:
    """Escreve ou confere os arquivos do mapa de memória da plataforma.

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
    tuple of (list of str, list of Path)
        Os problemas da conferência e os arquivos escritos; ambos vazios
        sem a seção `generate`.
    """
    if "generate" not in memory_map.load_platform(platform):
        return [], []
    if check:
        _, problems = memory_map.check_all(platform, root)
        return [str(problem) for problem in problems], []
    return [], memory_map.write_all(platform, root)


def _with_capacity(
    result: Generated, platform: Path, request: ProjectRequest
) -> Generated:
    """Junta ao projeto o relatório de cabimento.

    O cabimento é uma regra do validador (V11 a V13): passar de 100 % de
    um recurso recusa a geração, e o resto vira aviso. O módulo do
    validador é importado aqui porque ele importa, pelo leitor de
    configuração, o pacote que contém este módulo.

    Parameters
    ----------
    result : Generated
        O projeto gerado.
    platform : Path
        O `platform.yaml`.
    request : ProjectRequest
        O pedido, que dá a placa e as pastas do catálogo.

    Returns
    -------
    Generated
        O projeto com `capacity.json` e os avisos do cabimento, ou ele
        mesmo quando a família não tem calibração.

    Raises
    ------
    InputError
        Se o perfil passa da capacidade da placa.
    """
    data = read_platform_file(platform)
    catalog = Catalog(
        request.root / (request.boards_dir or "boards"),
        request.root / (request.chips_dir or "Memory/chips"),
    )
    report, findings = board_check.fit_report(
        data, resolve_board_name(data, request.board), catalog
    )
    errors = [str(item) for item in findings if item.level == "E"]
    if errors:
        raise InputError("; ".join(errors))
    if report is None:
        return result
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    return replace(
        result,
        files={**result.files, "capacity.json": text},
        warnings=[*result.warnings, *(str(item) for item in findings)],
    )


def build(request: ProjectRequest) -> ProjectResult:
    """Gera o projeto e o mapa de memória de uma plataforma.

    Parameters
    ----------
    request : ProjectRequest
        O pedido.

    Returns
    -------
    ProjectResult
        O projeto, a pasta, os problemas da conferência e os arquivos
        do mapa.

    Raises
    ------
    InputError, PinError, PllError, SdcError, SourcesError
        Se uma entrada é inválida.
    """
    root = request.root
    platform = root / request.platform
    out = root / request.out
    base = GenerateRequest(
        platform,
        request.board,
        root / (request.boards_dir or "boards"),
        root / (request.chips_dir or "Memory/chips"),
    )
    probe = generate(base)
    project = out / probe.folder
    targets = targets_of(platform, request.targets)
    sources_root = repository_root(platform, root)
    result = _with_capacity(
        generate(
            GenerateRequest(
                platform,
                request.board,
                base.boards_dir,
                base.chips_dir,
                sources_of(sources_root, targets, project),
                request.accept_inferred,
                request.seed,
            )
        ),
        platform,
        request,
    )
    if request.check:
        problems = check_project(out, result)
        map_problems, _ = _memory_map(root, platform, True)
        return ProjectResult(result, project, problems + map_problems)
    folder = write_project(out, result)
    _, written = _memory_map(root, platform, False)
    return ProjectResult(result, folder, [], written)


def request_from_config(
    root: Path,
    generate_cfg: dict[str, Any],
    board: str | None = None,
    seed: int = 5,
) -> ProjectRequest:
    """Monta o pedido da chave `quartus.generate` da configuração.

    Parameters
    ----------
    root : Path
        A raiz do espaço de trabalho.
    generate_cfg : dict of {str: Any}
        `platform` e `out`, e opcionalmente `boards_dir`, `chips_dir` e
        `accept_inferred_pins`.
    board : str or None
        A placa pedida na linha de comando.
    seed : int
        Semente do `.qsf`.

    Returns
    -------
    ProjectRequest
        O pedido, que escreve o projeto.
    """
    return ProjectRequest(
        root=root,
        platform=str(generate_cfg["platform"]),
        out=str(generate_cfg.get("out", "build")),
        board=board,
        boards_dir=generate_cfg.get("boards_dir"),
        chips_dir=generate_cfg.get("chips_dir"),
        seed=seed,
        accept_inferred=bool(generate_cfg.get("accept_inferred_pins")),
    )
