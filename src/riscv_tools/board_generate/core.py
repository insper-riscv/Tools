"""Compõe os geradores de um conceito cada num projeto do Quartus.

Este módulo só chama os geradores e junta o texto: o pacote de chip, os
pinos, o PLL, o `.sdc`, o projeto e o topo escrevem cada um o seu
arquivo. A pasta de saída é de construção e não é versionada.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from riscv_tools.board_clocks import clock_plan
from riscv_tools.board_inputs import BoardInputs, InputError, load_inputs
from riscv_tools.board_ports import PortPlan, build_ports
from riscv_tools.chip_package import (
    IoDelays,
    chip_io_delays,
    package_name,
    render_chip_package,
)
from riscv_tools.pin_assignments import render_pins
from riscv_tools.pll_generator import RenderedPll, generate_pll
from riscv_tools.quartus_project import ProjectSpec, render_qpf, render_qsf
from riscv_tools.sdc_generator import render_sdc
from riscv_tools.top_generator import TopSpec, render_top, top_name


@dataclass(frozen=True)
class GenerateRequest:
    """O pedido de uma geração.

    Attributes
    ----------
    platform_file : Path
        O `platform.yaml`.
    board : str or None
        A placa; `None` usa a da plataforma.
    boards_dir : Path
        A pasta `boards/`.
    chips_dir : Path
        O catálogo de chips.
    sources : tuple of str
        Fontes do fecho dos `provides`, como devem aparecer no `.qsf`.
    accept_inferred : bool
        Aceita construir com pino `inferred`.
    seed : int
        Semente do posicionamento.
    """

    platform_file: Path
    board: str | None
    boards_dir: Path
    chips_dir: Path
    sources: tuple[str, ...] = ()
    accept_inferred: bool = False
    seed: int = 5


@dataclass(frozen=True)
class Generated:
    """O resultado de uma geração.

    Attributes
    ----------
    name : str
        Nome do projeto (`<plataforma>_<placa>`).
    folder : str
        Pasta do projeto dentro da saída (`<plataforma>-<placa>`).
    files : dict of {str: str}
        Texto de cada arquivo, por nome.
    warnings : list of str
        Avisos achados.
    """

    name: str
    folder: str
    files: dict[str, str]
    warnings: list[str] = field(default_factory=lambda: [])


def _slug(text: str) -> str:
    """Troca os caracteres que o VHDL não aceita por `_`.

    Parameters
    ----------
    text : str
        O texto.

    Returns
    -------
    str
        Minúsculas com `_`.
    """
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _burst(chip: dict[str, Any], chips: int) -> int:
    """Dá o comprimento da rajada que completa uma palavra de 32 bits.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip de SDRAM.
    chips : int
        Quantos chips em paralelo.

    Returns
    -------
    int
        `32 / (chips * largura)`, no mínimo 1.
    """
    width = int(chip["organization"]["width"]) * chips
    return max(1, 32 // width)


def _chip_files(inputs: BoardInputs) -> tuple[dict[str, str], dict[str, str]]:
    """Gera o pacote de cada chip usado.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    tuple of (dict, dict)
        Os arquivos por nome e o nome do pacote por tipo de memória.
    """
    memories = cast(dict[str, Any], inputs.board.get("memories") or {})
    files: dict[str, str] = {}
    packages: dict[str, str] = {}
    for kind in ("sdram", "sram", "nor"):
        entry = memories.get(kind)
        if not entry or entry.get("chip") not in inputs.chips:
            continue
        chip = inputs.chips[str(entry["chip"])]
        burst = (
            _burst(chip, int(entry.get("chips", 1))) if kind == "sdram" else 1
        )
        name = package_name(str(chip["chip"]))
        files[f"{name}.vhd"] = render_chip_package(chip, burst)
        packages[kind] = name
    return files, packages


def _sdram_delays(inputs: BoardInputs, has_pin_clock: bool) -> IoDelays | None:
    """Lê os atrasos de E/S do chip de SDRAM, quando há relógio de pino.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    has_pin_clock : bool
        Se a plataforma tem o relógio que sai pelo pino da SDRAM.

    Returns
    -------
    IoDelays or None
        Os atrasos, ou `None` sem SDRAM de dispositivo.
    """
    memories = cast(dict[str, Any], inputs.board.get("memories") or {})
    sdram = memories.get("sdram")
    if sdram and has_pin_clock:
        return chip_io_delays(inputs.chips[str(sdram["chip"])])
    return None


def _qsf_and_qpf(
    inputs: BoardInputs,
    request: GenerateRequest,
    stem: str,
    parts: tuple[RenderedPll, tuple[str, ...], PortPlan],
) -> dict[str, str]:
    """Escreve o `.qsf` e o `.qpf` do projeto.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    request : GenerateRequest
        O pedido.
    stem : str
        Nome do projeto.
    parts : tuple
        O PLL escrito, os nomes dos pacotes de chip e as portas.

    Returns
    -------
    dict of {str: str}
        Os dois arquivos, por nome.
    """
    rendered, chip_names, ports = parts
    top = top_name(
        str(inputs.platform["platform"]), str(inputs.board["board"])
    )
    spec = ProjectSpec(
        name=stem,
        top=top,
        family=str(inputs.family["quartus_family"]),
        device=str(inputs.board["device"]),
        sdc=f"{stem}.sdc",
        sources=(
            *request.sources,
            f"{stem}_pll{rendered.suffix}",
            *chip_names,
            f"{top}.vhd",
        ),
        extra=(
            *rendered.qsf_lines,
            *render_pins(
                ports.ports,
                request.accept_inferred,
                bool(inputs.family.get("slew_rate", True)),
            ).splitlines(),
        ),
    )
    return {
        f"{stem}.qsf": render_qsf(spec, request.seed),
        f"{stem}.qpf": render_qpf(stem),
    }


def generate(request: GenerateRequest) -> Generated:
    """Gera os arquivos do projeto de uma plataforma numa placa.

    Parameters
    ----------
    request : GenerateRequest
        O pedido.

    Returns
    -------
    Generated
        Os arquivos e os avisos.

    Raises
    ------
    InputError
        Se a família não declara o PLL.
    """
    inputs = load_inputs(
        request.platform_file,
        request.board,
        request.boards_dir,
        request.chips_dir,
    )
    board_name = str(inputs.board["board"])
    platform_name = str(inputs.platform["platform"])
    stem = _slug(f"{platform_name}_{board_name}")
    plan = clock_plan(inputs)
    ports = build_ports(inputs)
    pll_info = cast(dict[str, Any], inputs.family.get("pll") or {})
    if not pll_info:
        raise InputError(f"family {inputs.board['family']!r}: no pll section")
    rendered, _ = generate_pll(
        f"{stem}_pll",
        plan.reference_mhz,
        plan.roles,
        pll_info,
        str(inputs.family["quartus_family"]),
    )
    chip_files, packages = _chip_files(inputs)
    top = top_name(platform_name, board_name)
    rendered_top = render_top(
        TopSpec(
            inputs.platform,
            plan,
            ports.ports,
            rendered.module,
            top,
            packages,
        )
    )
    files = {
        f"{stem}_pll{rendered.suffix}": rendered.text,
        f"{stem}.sdc": render_sdc(
            plan,
            ports.ports,
            _sdram_delays(inputs, plan.get("mem_pin") is not None),
            cast("str | None", pll_info.get("clock_node_pattern")),
        ),
        f"{top}.vhd": rendered_top.text,
        **chip_files,
        **_qsf_and_qpf(
            inputs, request, stem, (rendered, tuple(chip_files), ports)
        ),
    }
    return Generated(
        stem,
        f"{platform_name}-{board_name}",
        files,
        [*plan.warnings, *ports.warnings, *rendered_top.warnings],
    )


def write_project(out_dir: Path, generated: Generated) -> Path:
    """Escreve os arquivos gerados.

    Parameters
    ----------
    out_dir : Path
        A pasta de saída.
    generated : Generated
        O resultado de `generate`.

    Returns
    -------
    Path
        A pasta do projeto, `out_dir/<plataforma>-<placa>`.
    """
    project = out_dir / generated.folder
    project.mkdir(parents=True, exist_ok=True)
    for name, text in generated.files.items():
        (project / name).write_text(text, encoding="utf-8")
    return project


def check_project(out_dir: Path, generated: Generated) -> list[str]:
    """Compara os arquivos gerados com os da pasta de saída.

    Parameters
    ----------
    out_dir : Path
        A pasta de saída.
    generated : Generated
        O resultado de `generate`.

    Returns
    -------
    list of str
        Um problema por arquivo ausente ou diferente; vazio quando a
        pasta está em dia.
    """
    project = out_dir / generated.folder
    problems: list[str] = []
    for name, text in generated.files.items():
        path = project / name
        if not path.is_file():
            problems.append(f"{path}: missing")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"{path}: out of date")
    return problems
