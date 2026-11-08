"""Escreve o projeto do Quartus: revisão, dispositivo e fontes.

As atribuições por pino não vêm daqui, mas do gerador de pinos, e a
lista de fontes vem do `sources` (o fecho dos `provides`); este módulo
só a escreve com o tipo de arquivo certo.
"""

from dataclasses import dataclass, field

# Tipo de atribuição de cada extensão de fonte.
_SOURCE_KIND = {
    ".vhd": "VHDL_FILE",
    ".vhdl": "VHDL_FILE",
    ".v": "VERILOG_FILE",
    ".sv": "SYSTEMVERILOG_FILE",
    ".qip": "QIP_FILE",
}


@dataclass(frozen=True)
class ProjectSpec:
    """O que o projeto precisa saber.

    Attributes
    ----------
    name : str
        Nome da revisão (e do `.qpf`).
    top : str
        Entidade de topo.
    family : str
        Texto da família do Quartus (`Cyclone V`).
    device : str
        Dispositivo completo.
    sdc : str
        Caminho do `.sdc`, relativo ao projeto.
    sources : tuple of str
        Fontes, em ordem de análise, relativas ao projeto.
    extra : tuple of str
        Linhas a acrescentar ao fim (atribuições do PLL, pinos).
    """

    name: str
    top: str
    family: str
    device: str
    sdc: str
    sources: tuple[str, ...]
    extra: tuple[str, ...] = field(default_factory=tuple)


def render_qpf(name: str) -> str:
    """Escreve o `.qpf`.

    Parameters
    ----------
    name : str
        Nome da revisão.

    Returns
    -------
    str
        O texto do arquivo.
    """
    return (
        "# Projeto gerado pelo riscv-tools (não edite).\n"
        f'PROJECT_REVISION = "{name}"\n'
    )


def _source_line(path: str) -> str:
    """Escreve a atribuição de uma fonte.

    Parameters
    ----------
    path : str
        Caminho da fonte.

    Returns
    -------
    str
        A linha `set_global_assignment`.

    Raises
    ------
    ValueError
        Se a extensão não é de fonte conhecida.
    """
    suffix = "." + path.rsplit(".", 1)[-1].lower()
    kind = _SOURCE_KIND.get(suffix)
    if kind is None:
        raise ValueError(f"source {path}: unknown extension")
    return f"set_global_assignment -name {kind} {path}"


def render_qsf(spec: ProjectSpec, seed: int = 5) -> str:
    """Escreve o `.qsf`, sem as atribuições de pino.

    Parameters
    ----------
    spec : ProjectSpec
        O projeto.
    seed : int, optional
        Semente do posicionamento, por padrão 5.

    Returns
    -------
    str
        O texto do arquivo.
    """
    name = "set_global_assignment -name"
    lines = [
        "# Projeto gerado pelo riscv-tools (não edite).",
        f'{name} FAMILY "{spec.family}"',
        f"{name} DEVICE {spec.device}",
        f"{name} TOP_LEVEL_ENTITY {spec.top}",
        f"{name} PROJECT_OUTPUT_DIRECTORY output_files",
        f"{name} SDC_FILE {spec.sdc}",
        f"{name} VHDL_INPUT_VERSION VHDL_2008",
        f"{name} ERROR_CHECK_FREQUENCY_DIVISOR 256",
        f"{name} TIMING_ANALYZER_MULTICORNER_ANALYSIS ON",
        f"{name} NUM_PARALLEL_PROCESSORS ALL",
        f'{name} OPTIMIZATION_MODE "HIGH PERFORMANCE EFFORT"',
        f"{name} SEED {seed}",
        "",
        *(_source_line(path) for path in spec.sources),
        *spec.extra,
    ]
    return "\n".join(lines) + "\n"
