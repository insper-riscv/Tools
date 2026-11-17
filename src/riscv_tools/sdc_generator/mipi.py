"""Escreve as restrições da câmera MIPI CSI-2.

O relógio do D-PHY (`CLK`) vem da câmera, assíncrono ao SoC, e sai do
pino LVDS direto para o registrador DDR de entrada. O periférico leva o
pedido de captura, o fim, os erros e o estado entre os dois domínios
por sincronizadores, e os vetores parados que cruzam com eles não têm
requisito, então o relógio da câmera forma um grupo assíncrono ao SoC.
"""

from riscv_tools.board_ports import Port

# Período de 200 MHz, em nanossegundos: o teto que a restrição cobre,
# o que dá 400 Mbit/s por lane com as duas bordas.
MIPI_PERIOD_NS = 5


def mipi_section(ports: tuple[Port, ...], soc_nodes: list[str]) -> list[str]:
    """Escreve as restrições do relógio da câmera.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    soc_nodes : list of str
        Nós dos relógios do SoC.

    Returns
    -------
    list of str
        As linhas; vazia sem o pino `clk` de uma câmera.
    """
    clocks = [p for p in ports if p.role == "mipi" and p.pin == "clk"]
    if not clocks:
        return []
    soc = " ".join(soc_nodes)
    lines = [
        "",
        "# Câmera MIPI: o relógio do D-PHY vem da câmera, e o registrador",
        "# DDR amostra as lanes LVDS nas duas bordas dele.",
    ]
    names = [p.name for p in clocks]
    lines += [
        f"create_clock -name {name} -period {MIPI_PERIOD_NS:.3f} "
        f"[get_ports {name}]"
        for name in names
    ]
    camera = " ".join(names)
    lines.append(
        f"set_clock_groups -asynchronous -group [get_clocks {{{camera}}}]"
        f" -group [get_clocks {{{soc}}}]"
    )
    return lines
