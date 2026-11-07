"""Cálculo dos contadores de um PLL: o menor VCO que atende."""

from fractions import Fraction
from typing import Any, cast

from riscv_tools.board_clocks import ClockRole
from riscv_tools.pll_generator.types import (
    PllError,
    PllOutput,
    PllSolution,
    format_mhz,
)

_PS_PER_US = 1_000_000
# Fases do PLL são múltiplos de um oitavo do período do VCO.
_PHASE_STEPS = 8
_N_MAX = 8
_M_MAX = 512
_C_MAX = 511


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
            f"{r.role} {format_mhz(r.mhz)} MHz @ {r.phase_ps} ps"
            for r in requests
        )
        raise PllError(
            f"E no VCO in [{low}, {high}] MHz from "
            f"{format_mhz(reference_mhz)} "
            f"MHz gives integer dividers and exact phase steps for: {wanted}"
        )
    vco, n, m, dividers = found
    outputs = tuple(
        PllOutput(r.role, i, r.mhz, r.phase_ps, dividers[i])
        for i, r in enumerate(requests)
    )
    return PllSolution(reference_mhz, n, m, vco, outputs)
