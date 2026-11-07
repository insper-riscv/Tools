"""Texto VHDL dos backends de memória que o topo da placa instancia.

Cada backend é uma composição de entidades que já existem no Memory,
com os nomes e as portas reais delas (`flash_chip`, `flash`,
`flash_loader`, `flash_jtag_shell`, `onchip_ram_port`, `ram`,
`sdram_cpu_bridge`, `sdram_arbiter`, `sdram_dbg_master`,
`sdram_jtag_shell`, `sdram_ctrl` e `nor_flash_ctrl`). O texto de cada
um fica em `templates/`, com `{campo}` onde o gerador preenche. Um
backend sem entidade ainda (`sram`) não gera instância: o topo avisa e
deixa a região parada.
"""

from pathlib import Path

# Larguras de dados da SDRAM que o controlador suporta: um chip de 16
# bits ou dois lado a lado.
SDRAM_DQ_WIDTHS = (16, 32)

_TEMPLATES = Path(__file__).resolve().parent / "templates"


def template(name: str) -> str:
    """Lê o modelo de texto de um backend.

    Parameters
    ----------
    name : str
        Nome do modelo, sem a extensão `.vhd.in`.

    Returns
    -------
    str
        O texto do modelo.
    """
    return (_TEMPLATES / f"{name}.vhd.in").read_text(encoding="utf-8")
