"""Escreve as restrições do Ethernet RGMII.

O RXC vem do PHY e é um relógio de entrada de 125 MHz; o relógio de
envio sai do PLL e, pelo registrador DDR, vai ao pino `GTX_CLK`, que
vira um relógio gerado. Os três domínios do MAC (sistema, recepção e
envio) só se encontram em FIFOs assíncronas e sincronizadores dentro da
entidade, então os relógios do Ethernet formam um grupo assíncrono ao
resto do SoC. MDC, MDIO, INT_N e RESET_N são lentos e não têm requisito.
"""

from riscv_tools.board_ports import Port

# Período de 125 MHz, em nanossegundos.
RGMII_PERIOD_NS = 8
# Pinos lentos do papel, sem requisito de tempo.
SLOW_PINS = frozenset({"mdc", "mdio", "int_n", "rst_n"})


def _owners(ports: tuple[Port, ...]) -> list[str]:
    """Lista os donos de portas RGMII (as que têm o pino `gtx_clk`)."""
    return [p.owner for p in ports if p.role == "eth" and p.pin == "gtx_clk"]


def _pin(ports: tuple[Port, ...], owner: str, pin: str) -> Port:
    """Acha a porta de um pino do papel de um periférico."""
    return next(p for p in ports if p.owner == owner and p.pin == pin)


def _slow(ports: tuple[Port, ...], owner: str) -> list[str]:
    """Escreve os caminhos falsos dos pinos lentos de um MAC."""
    lines: list[str] = []
    slow = [p for p in ports if p.owner == owner and p.pin in SLOW_PINS]
    for port in slow:
        name = f"{port.name}[*]" if port.vector else port.name
        ends = {"in": ("from",), "out": ("to  ",)}.get(
            port.direction, ("from", "to  ")
        )
        lines += [f"set_false_path -{e} [get_ports {{{name}}}]" for e in ends]
    return lines


def eth_section(
    ports: tuple[Port, ...],
    tx_node: str,
    tx_dly_node: str | None,
    soc_nodes: list[str],
) -> list[str]:
    """Escreve as restrições dos MACs RGMII do topo.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    tx_node : str
        Nó do relógio de envio livre do PLL.
    tx_dly_node : str or None
        Nó do relógio de envio deslocado; `None` quando o plano não o
        tem e o `GTX_CLK` sai do relógio livre.
    soc_nodes : list of str
        Nós dos relógios do SoC (núcleo, busca e controlador).

    Returns
    -------
    list of str
        As linhas; vazia sem MAC RGMII.
    """
    owners = _owners(ports)
    if not owners:
        return []
    source = tx_dly_node or tx_node
    lines = [
        "",
        "# Ethernet RGMII: o RXC é relógio de entrada do PHY, e o GTX_CLK é o",
        "# relógio de envio do PLL, que sai pelo registrador DDR do pino.",
    ]
    eth_clocks = [tx_node, *([tx_dly_node] if tx_dly_node else [])]
    for owner in owners:
        rx = _pin(ports, owner, "rx_clk").name
        gtx = _pin(ports, owner, "gtx_clk").name
        lines += [
            f"create_clock -name {rx} -period {RGMII_PERIOD_NS:.3f} "
            f"[get_ports {rx}]",
            f"create_generated_clock -name {gtx}_pin -source "
            f"[get_pins {{{source}}}] [get_ports {gtx}]",
        ]
        eth_clocks += [rx, f"{gtx}_pin"]
    eth = " ".join(eth_clocks)
    soc = " ".join(soc_nodes)
    lines += [
        "",
        "# Sistema, recepção e envio só se cruzam em FIFOs e sincronizadores",
        "# da entidade, então os relógios do Ethernet são assíncronos ao SoC.",
        f"set_clock_groups -asynchronous -group [get_clocks {{{eth}}}]"
        f" -group [get_clocks {{{soc}}}]",
        "",
        "# MDC, MDIO, INT_N e RESET_N são lentos e não têm requisito.",
    ]
    for owner in owners:
        lines += _slow(ports, owner)
    return lines
