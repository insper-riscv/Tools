"""Tipos do gerador de PLL: erros, saídas, solução e texto escrito."""

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction


class PllError(ValueError):
    """O PLL pedido não existe na família."""


class PllIpPendingError(PllError):
    """A primitiva da família ainda não tem escritor."""


@dataclass(frozen=True)
class PllOutput:
    """Uma saída do PLL.

    Attributes
    ----------
    role : str
        Papel do relógio.
    index : int
        Posição da saída (`outclk_<index>`).
    mhz : Fraction
        Frequência.
    phase_ps : int
        Fase em picossegundos.
    divider : int
        Divisor `C` da saída contra o VCO.
    """

    role: str
    index: int
    mhz: Fraction
    phase_ps: int
    divider: int


@dataclass(frozen=True)
class PllSolution:
    """Os contadores de um PLL.

    Attributes
    ----------
    reference_mhz : Fraction
        Frequência de entrada.
    n : int
        Divisor de entrada.
    m : int
        Multiplicador do laço.
    vco_mhz : Fraction
        Frequência do VCO.
    outputs : tuple of PllOutput
        As saídas, na ordem pedida.
    """

    reference_mhz: Fraction
    n: int
    m: int
    vco_mhz: Fraction
    outputs: tuple[PllOutput, ...]


@dataclass(frozen=True)
class RenderedPll:
    """O PLL escrito.

    Attributes
    ----------
    module : str
        Nome do módulo.
    suffix : str
        Extensão do arquivo, com ponto.
    text : str
        O conteúdo.
    qsf_lines : tuple of str
        Atribuições de instância que o `.qsf` precisa para o PLL.
    """

    module: str
    suffix: str
    text: str
    qsf_lines: tuple[str, ...]


# Escritor de uma primitiva: módulo, solução e família do Quartus.
Renderer = Callable[[str, PllSolution, str], RenderedPll]


def format_mhz(value: Fraction) -> str:
    """Escreve uma frequência com seis casas.

    Parameters
    ----------
    value : Fraction
        Frequência em MHz.

    Returns
    -------
    str
        Por exemplo `100.000000`.
    """
    return f"{float(value):.6f}"
