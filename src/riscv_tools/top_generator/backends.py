"""Texto VHDL dos backends de memória que o topo da placa instancia.

Cada backend é uma composição de entidades que já existem no Memory,
com os nomes e as portas reais delas (`flash_chip`, `flash`,
`flash_loader`, `flash_jtag_shell`, `onchip_ram_port`, `ram`,
`sdram_cpu_bridge`, `sdram_arbiter`, `sdram_dbg_master`,
`sdram_jtag_shell` e `sdram_ctrl`). O texto de cada um fica em
`templates/`, com `{campo}` onde o gerador preenche. Um backend sem
entidade ainda (`nor`, `sram`, SDRAM de largura diferente de 16 bits)
não gera instância: o topo avisa e deixa a região parada.
"""

from pathlib import Path

# Largura de dados da SDRAM que o controlador atual suporta.
SDRAM_DQ_WIDTH = 16

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
