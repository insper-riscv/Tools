"""Escolhe o escritor da primitiva da família e gera o PLL.

O cálculo (`solve`) vale para toda família. O texto da primitiva fica
num escritor por IP, registrado em `RENDERERS`: `altera_pll` (Cyclone V)
e `altpll` (Cyclone IV E, MAX 10 e Cyclone 10 LP), conforme a medição
M.0.2. Outra primitiva entra por `register_renderer`.
"""

from fractions import Fraction
from typing import Any

from riscv_tools.board_clocks import ClockRole
from riscv_tools.pll_generator.altera_pll import render_altera_pll
from riscv_tools.pll_generator.altpll import render_altpll
from riscv_tools.pll_generator.solve import solve
from riscv_tools.pll_generator.types import (
    PllIpPendingError,
    PllSolution,
    RenderedPll,
    Renderer,
)

RENDERERS: dict[str, Renderer] = {
    "altera_pll": render_altera_pll,
    "altpll": render_altpll,
}


def register_renderer(ip: str, renderer: Renderer) -> None:
    """Registra o escritor de uma primitiva de PLL.

    Parameters
    ----------
    ip : str
        O IP, como o campo `pll.ip` da família (`altpll`).
    renderer : Callable
        Função `(módulo, solução) -> RenderedPll`.
    """
    RENDERERS[ip] = renderer


def renderer_for(ip: str) -> Renderer:
    """Busca o escritor de uma primitiva.

    Parameters
    ----------
    ip : str
        O IP da família.

    Returns
    -------
    Callable
        O escritor registrado.

    Raises
    ------
    PllIpPendingError
        Se o IP não tem escritor.
    """
    try:
        return RENDERERS[ip]
    except KeyError as error:
        raise PllIpPendingError(
            f"PLL primitive {ip!r} has no renderer yet (measurement "
            f"M.0.2); register one with register_renderer({ip!r}, ...)"
        ) from error


def generate_pll(
    module: str,
    reference_mhz: Fraction,
    requests: tuple[ClockRole, ...],
    pll: dict[str, Any],
    quartus_family: str,
) -> tuple[RenderedPll, PllSolution]:
    """Calcula e escreve o PLL de uma placa.

    Parameters
    ----------
    module : str
        Nome do módulo gerado.
    reference_mhz : Fraction
        Frequência de entrada.
    requests : tuple of ClockRole
        Os relógios pedidos.
    pll : dict of {str: Any}
        A seção `pll` da família (`ip`, `vco_mhz`, `outputs_max`).
    quartus_family : str
        O texto da família no Quartus (`Cyclone IV E`).

    Returns
    -------
    tuple of (RenderedPll, PllSolution)
        O arquivo e os contadores.
    """
    writer = renderer_for(str(pll["ip"]))
    solution = solve(reference_mhz, requests, pll)
    return writer(module, solution, quartus_family), solution
