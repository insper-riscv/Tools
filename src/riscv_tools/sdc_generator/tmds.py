"""Escreve as restrições da saída HDMI com TMDS direto.

Os pares de dados e o par de relógio saem de um registrador DDR no
relógio serial (cinco vezes o de pixel, do mesmo PLL), e o monitor
recupera o relógio do próprio par, então os pinos não têm requisito de
tempo contra um relógio da placa. O `hpd` vem do conector, assíncrono.
Os relógios `pixel` e `pixel_x5` formam o domínio de vídeo, assíncrono
ao SoC, e a seção de relógios de pixel do `.sdc` os cobre.
"""

from riscv_tools.board_ports import Port
from riscv_tools.sdc_generator.slow_pins import slow_pin_lines


def tmds_section(ports: tuple[Port, ...]) -> list[str]:
    """Escreve os caminhos falsos dos pinos da saída TMDS.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.

    Returns
    -------
    list of str
        As linhas; vazia sem saída TMDS.
    """
    return slow_pin_lines(
        ports,
        "hdmi_tmds",
        "HDMI TMDS direto: os pares saem do registrador DDR no relógio "
        "serial e o monitor recupera o relógio do par, e o hpd é "
        "assíncrono, então os pinos não têm requisito de tempo.",
    )
