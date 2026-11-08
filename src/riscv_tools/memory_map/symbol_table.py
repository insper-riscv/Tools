"""Junta os símbolos de todas as seções do mapa de uma plataforma."""

from typing import Any

from riscv_tools.memory_map import banks, interrupts, sdram_clock
from riscv_tools.memory_map.core import symbols


def symbol_table(platform: dict[str, Any]) -> dict[str, int]:
    """Reúne os símbolos do mapa, bancos, clock e interrupções.

    Parameters
    ----------
    platform : dict of {str: Any}
        A plataforma carregada.

    Returns
    -------
    dict of {str: int}
        Nome do símbolo e valor.
    """
    return (
        symbols(platform)
        | banks.symbols(platform)
        | sdram_clock.symbols(platform)
        | interrupts.symbols(platform)
    )
