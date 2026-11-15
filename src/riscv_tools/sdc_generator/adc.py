"""Escreve as restrições do ADC interno do MAX 10.

O pino `ADC_CLK_10` é um relógio de entrada de 10 MHz que alimenta o
PLL do conversor. O domínio do conversor só encontra o do SoC nas
interfaces de comando e resposta do núcleo, que o periférico
sincroniza, então os dois são assíncronos.
"""

from riscv_tools.board_ports import Port

# Período de 10 MHz, em nanossegundos.
ADC_PERIOD_NS = 100


def adc_section(ports: tuple[Port, ...], soc_nodes: list[str]) -> list[str]:
    """Escreve as restrições do relógio do ADC.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    soc_nodes : list of str
        Nós dos relógios do SoC.

    Returns
    -------
    list of str
        As linhas; vazia sem o pino `clk10` de um ADC.
    """
    found = [p for p in ports if p.role == "adc" and p.pin == "clk10"]
    if not found:
        return []
    pin = found[0].name
    soc = " ".join(soc_nodes)
    return [
        "",
        "# ADC interno do MAX 10: o ADC_CLK_10 alimenta o PLL do conversor.",
        f"create_clock -name {pin} -period {ADC_PERIOD_NS:.3f} "
        f"[get_ports {pin}]",
        "derive_pll_clocks",
        "set_clock_groups -asynchronous "
        f"-group [get_clocks {{{pin} *max10_adc_pll*}}] "
        f"-group [get_clocks {{{soc}}}]",
    ]
