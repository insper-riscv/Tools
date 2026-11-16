"""Escreve as restrições do módulo Wi-Fi NINA.

O SPI, a UART, o reset, o GPIO0 e o ACK do módulo são lentos e o
módulo tem relógio próprio, então os pinos não têm requisito de tempo.
"""

from riscv_tools.board_ports import Port
from riscv_tools.sdc_generator.slow_pins import slow_pin_lines


def wifi_section(ports: tuple[Port, ...]) -> list[str]:
    """Escreve os caminhos falsos dos pinos do módulo Wi-Fi.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.

    Returns
    -------
    list of str
        As linhas; vazia sem módulo Wi-Fi.
    """
    return slow_pin_lines(
        ports,
        "wifi",
        "Módulo Wi-Fi: os pinos de controle, SPI e UART são lentos e "
        "assíncronos ao relógio do núcleo, sem requisito de tempo.",
    )
