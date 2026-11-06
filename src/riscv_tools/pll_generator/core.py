"""Calcula os divisores de um PLL e escreve a primitiva da família.

O cálculo (`solve`) vale para toda família. O texto da primitiva fica
num escritor por IP, registrado em `RENDERERS`: `altera_pll` (Cyclone V
e Cyclone V SoC) está pronto, e `altpll` (Cyclone IV E, MAX 10 e
Cyclone 10 LP) é o ponto de extensão que espera a medição da primitiva
por família; quem a fizer chama `register_renderer("altpll", ...)`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, cast

from riscv_tools.board_clocks import ClockRole

_PS_PER_US = 1_000_000
# Fases do PLL são múltiplos de um oitavo do período do VCO.
_PHASE_STEPS = 8
_N_MAX = 8
_M_MAX = 512
_C_MAX = 511


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


Renderer = Callable[[str, PllSolution], RenderedPll]


def _mhz(value: Fraction) -> str:
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


def _altera_pll_outputs(solution: PllSolution) -> str:
    """Escreve os parâmetros por saída do `altera_pll`.

    Parameters
    ----------
    solution : PllSolution
        Os contadores.

    Returns
    -------
    str
        As linhas de parâmetro.
    """
    lines: list[str] = []
    for out in solution.outputs:
        lines += [
            f'\t\t.output_clock_frequency{out.index}("{_mhz(out.mhz)} MHz"),',
            f'\t\t.phase_shift{out.index}("{out.phase_ps} ps"),',
            f"\t\t.duty_cycle{out.index}(50),",
        ]
    return "\n".join(lines)


def render_altera_pll(module: str, solution: PllSolution) -> RenderedPll:
    """Escreve o PLL na primitiva `altera_pll`.

    Parameters
    ----------
    module : str
        Nome do módulo.
    solution : PllSolution
        Os contadores.

    Returns
    -------
    RenderedPll
        O módulo Verilog com as portas `refclk`, `rst`, `outclk_<i>` e
        `locked`.
    """
    count = len(solution.outputs)
    ports = "".join(f"\toutput wire outclk_{i},\n" for i in range(count))
    names = ", ".join(f"outclk_{i}" for i in reversed(range(count)))
    notes = "\n".join(
        f"//   outclk_{o.index}  {_mhz(o.mhz)} MHz, fase {o.phase_ps} ps  "
        f"{o.role}"
        for o in solution.outputs
    )
    vco = _mhz(solution.vco_mhz)
    text = f"""// PLL gerado pelo riscv-tools (não edite): VCO de {vco} MHz
// a partir de {_mhz(solution.reference_mhz)} MHz.
//
{notes}
`timescale 1ns/10ps
module {module} (
\tinput  wire refclk,
\tinput  wire rst,
{ports}\toutput wire locked
);

\taltera_pll #(
\t\t.fractional_vco_multiplier("false"),
\t\t.reference_clock_frequency("{_mhz(solution.reference_mhz)} MHz"),
\t\t.operation_mode("direct"),
\t\t.number_of_clocks({count}),
{_altera_pll_outputs(solution)}
\t\t.pll_type("General"),
\t\t.pll_subtype("General")
\t) altera_pll_i (
\t\t.rst\t(rst),
\t\t.outclk\t({{{names}}}),
\t\t.locked\t(locked),
\t\t.fboutclk\t( ),
\t\t.fbclk\t(1'b0),
\t\t.refclk\t(refclk)
\t);

endmodule
"""
    assign = "set_instance_assignment -name"
    target = f'"*{module}*|altera_pll:altera_pll_i*|*"'
    return RenderedPll(
        module,
        ".v",
        text,
        (
            f"{assign} PLL_COMPENSATION_MODE DIRECT -to {target}",
            f"{assign} PLL_AUTO_RESET OFF -to {target}",
            f"{assign} PLL_BANDWIDTH_PRESET AUTO -to {target}",
        ),
    )


RENDERERS: dict[str, Renderer] = {"altera_pll": render_altera_pll}


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


def _divider(vco: Fraction, mhz: Fraction) -> int | None:
    """Dá o divisor inteiro de uma saída, se existir.

    Parameters
    ----------
    vco : Fraction
        Frequência do VCO.
    mhz : Fraction
        Frequência pedida.

    Returns
    -------
    int or None
        `vco / mhz` se é inteiro de 1 a 511, senão `None`.
    """
    ratio = vco / mhz
    if ratio.denominator != 1 or not 1 <= ratio <= _C_MAX:
        return None
    return int(ratio)


def _phase_ok(vco: Fraction, phase_ps: int) -> bool:
    """Diz se a fase é múltiplo do passo de fase do VCO.

    Parameters
    ----------
    vco : Fraction
        Frequência do VCO.
    phase_ps : int
        Fase pedida.

    Returns
    -------
    bool
        Verdadeiro quando a fase cai num passo exato.
    """
    step = Fraction(_PS_PER_US) / (vco * _PHASE_STEPS)
    return (Fraction(phase_ps) / step).denominator == 1


def _dividers(
    vco: Fraction, requests: tuple[ClockRole, ...]
) -> tuple[int, ...] | None:
    """Dá os divisores de todas as saídas, se o VCO atende todas.

    Parameters
    ----------
    vco : Fraction
        Frequência do VCO.
    requests : tuple of ClockRole
        Os relógios pedidos.

    Returns
    -------
    tuple of int or None
        Um divisor por saída, ou `None` se uma frequência não divide o
        VCO ou uma fase não cai num passo exato.
    """
    if not all(_phase_ok(vco, r.phase_ps) for r in requests):
        return None
    found = [_divider(vco, r.mhz) for r in requests]
    if any(d is None for d in found):
        return None
    return tuple(cast(list[int], found))


def _lowest_vco(
    reference_mhz: Fraction,
    requests: tuple[ClockRole, ...],
    vco_range: tuple[Fraction, Fraction],
) -> tuple[Fraction, int, int, tuple[int, ...]] | None:
    """Busca o menor VCO que atende todos os pedidos.

    Parameters
    ----------
    reference_mhz : Fraction
        Frequência de entrada.
    requests : tuple of ClockRole
        Os relógios pedidos.
    vco_range : tuple of (Fraction, Fraction)
        Faixa do VCO da família.

    Returns
    -------
    tuple or None
        VCO, N, M e os divisores, ou `None` se nenhum VCO atende.
    """
    low, high = vco_range
    candidates = sorted(
        (reference_mhz * m / n, n, m)
        for n in range(1, _N_MAX + 1)
        for m in range(1, _M_MAX + 1)
        if low <= reference_mhz * m / n <= high
    )
    for vco, n, m in candidates:
        dividers = _dividers(vco, requests)
        if dividers is not None:
            return vco, n, m, dividers
    return None


def solve(
    reference_mhz: Fraction,
    requests: tuple[ClockRole, ...],
    pll: dict[str, Any],
) -> PllSolution:
    """Acha os contadores do menor VCO que atende todos os pedidos.

    Parameters
    ----------
    reference_mhz : Fraction
        Frequência de entrada.
    requests : tuple of ClockRole
        Os relógios pedidos.
    pll : dict of {str: Any}
        A seção `pll` da família (`vco_mhz`, `outputs_max`).

    Returns
    -------
    PllSolution
        O VCO mais baixo cujo divisor de cada saída é inteiro e cujas
        fases caem em passos exatos.

    Raises
    ------
    PllError
        Se há mais saídas que a família oferece ou nenhum VCO atende
        (regra V7).
    """
    low, high = (Fraction(str(v)) for v in cast(list[Any], pll["vco_mhz"]))
    limit = int(pll.get("outputs_max", len(requests)))
    if len(requests) > limit:
        raise PllError(
            f"E platform needs {len(requests)} PLL outputs; the family "
            f"provides {limit}"
        )
    found = _lowest_vco(reference_mhz, requests, (low, high))
    if found is None:
        wanted = ", ".join(
            f"{r.role} {_mhz(r.mhz)} MHz @ {r.phase_ps} ps" for r in requests
        )
        raise PllError(
            f"E no VCO in [{low}, {high}] MHz from {_mhz(reference_mhz)} "
            f"MHz gives integer dividers and exact phase steps for: {wanted}"
        )
    vco, n, m, dividers = found
    outputs = tuple(
        PllOutput(r.role, i, r.mhz, r.phase_ps, dividers[i])
        for i, r in enumerate(requests)
    )
    return PllSolution(reference_mhz, n, m, vco, outputs)


def generate_pll(
    module: str,
    reference_mhz: Fraction,
    requests: tuple[ClockRole, ...],
    pll: dict[str, Any],
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

    Returns
    -------
    tuple of (RenderedPll, PllSolution)
        O arquivo e os contadores.
    """
    writer = renderer_for(str(pll["ip"]))
    solution = solve(reference_mhz, requests, pll)
    return writer(module, solution), solution
