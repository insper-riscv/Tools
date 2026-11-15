"""Escreve as restrições do módulo Wi-Fi NINA.

O SPI, a UART, o reset, o GPIO0 e o ACK do módulo são lentos e o
módulo tem relógio próprio, então os pinos não têm requisito de tempo.
"""

from riscv_tools.board_ports import Port


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
    wifi = [p for p in ports if p.role == "wifi"]
    if not wifi:
        return []
    lines = [
        "",
        "# Módulo Wi-Fi: os pinos de controle, SPI e UART são lentos e",
        "# assíncronos ao relógio do núcleo, sem requisito de tempo.",
    ]
    for port in wifi:
        name = f"{port.name}[*]" if port.vector else port.name
        if port.direction in ("in", "inout"):
            lines.append(f"set_false_path -from [get_ports {{{name}}}]")
        if port.direction in ("out", "inout"):
            lines.append(f"set_false_path -to   [get_ports {{{name}}}]")
    return lines
