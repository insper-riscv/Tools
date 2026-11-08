"""Cabeçalho comum dos módulos Verilog que embrulham o PLL."""


def module_head(notes: str, module: str, ports: str) -> str:
    """Escreve a escala de tempo e a declaração do módulo do PLL.

    Parameters
    ----------
    notes : str
        As linhas de comentário com as saídas do PLL.
    module : str
        O nome do módulo.
    ports : str
        As portas de saída de relógio, uma por linha.

    Returns
    -------
    str
        Do comentário das saídas até o `);` da declaração, com quebra de
        linha no fim.
    """
    return f"""{notes}
`timescale 1ns/10ps
module {module} (
\tinput  wire refclk,
\tinput  wire rst,
{ports}\toutput wire locked
);
"""
