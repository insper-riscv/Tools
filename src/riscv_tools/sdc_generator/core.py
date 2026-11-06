"""Escreve as restrições de tempo.

A ordem é a do documento 04: relógios de entrada, relógios do PLL,
relógio gerado do pino da memória, atrasos de E/S do chip, caminhos de
leitura da memória, cruzamentos de domínio e caminhos falsos de E/S
lentas.
"""

from riscv_tools.board_clocks import PLL_INSTANCE, ClockPlan
from riscv_tools.board_ports import Port, memory_clock_port
from riscv_tools.chip_package import IoDelays

# Frequência do relógio da JTAG só entra como domínio; o nome é o do
# Quartus.
JTAG_CLOCK = "altera_reserved_tck"


class SdcError(ValueError):
    """A família não traz o que o `.sdc` precisa."""


def _num(value: float) -> str:
    """Escreve um número do `.sdc` sem zeros inúteis.

    Parameters
    ----------
    value : float
        O número.

    Returns
    -------
    str
        Por exemplo `1.5` ou `10`.
    """
    return f"{value:g}"


def _node(pattern: str | None, index: int) -> str:
    """Dá o nó de relógio de uma saída do PLL.

    Parameters
    ----------
    pattern : str or None
        O `clock_node_pattern` da família.
    index : int
        Índice da saída.

    Returns
    -------
    str
        O nome do nó.

    Raises
    ------
    SdcError
        Se a família não tem o padrão.
    """
    if not pattern:
        raise SdcError(
            "family pll.clock_node_pattern is missing (measurement M.0.2)"
        )
    return pattern.format(instance=PLL_INSTANCE, index=index)


def _targets(ports: list[Port], direction: tuple[str, ...]) -> str:
    """Lista os alvos `get_ports` das portas de certas direções.

    Parameters
    ----------
    ports : list of Port
        As portas candidatas.
    direction : tuple of str
        Direções aceitas.

    Returns
    -------
    str
        Os nomes separados por espaço, vetores como `NOME[*]`.
    """
    return " ".join(
        f"{p.name}[*]" if p.vector else p.name
        for p in ports
        if p.direction in direction
    )


def _memory_section(
    plan: ClockPlan,
    ports: tuple[Port, ...],
    delays: IoDelays,
    pattern: str | None,
) -> list[str]:
    """Escreve a parte do relógio de pino e dos atrasos de E/S.

    Parameters
    ----------
    plan : ClockPlan
        Os relógios.
    ports : tuple of Port
        As portas do topo.
    delays : IoDelays
        Os atrasos do chip.
    pattern : str or None
        O padrão de nó da família.

    Returns
    -------
    list of str
        As linhas.

    Raises
    ------
    SdcError
        Se a SDRAM não tem porta de relógio de pino.
    """
    pin = memory_clock_port(ports, "sdram")
    if pin is None:
        raise SdcError("sdram without a clock pin (name ending in CLK)")
    pin_clock = f"{pin.name}_pin"
    group = [p for p in ports if p.role == "sdram" and p is not pin]
    mem = _node(pattern, plan.index("mem"))
    src = _node(pattern, plan.index("mem_pin"))
    return [
        "# O relógio que sai pelo pino confere o setup e o hold da memória;",
        "# os atrasos são os do chip do catálogo.",
        f"create_generated_clock -name {pin_clock} -source "
        f"[get_pins {{{src}}}] [get_ports {pin.name}]",
        "",
        f"set dram_out [get_ports {{{_targets(group, ('out', 'inout'))}}}]",
        f"set_output_delay -clock {pin_clock} -max "
        f"{_num(delays.output_max_ns)} $dram_out",
        f"set_output_delay -clock {pin_clock} -min "
        f"{_num(delays.output_min_ns)} $dram_out",
        f"set_input_delay  -clock {pin_clock} -max "
        f"{_num(delays.input_max_ns)} "
        f"[get_ports {{{_targets(group, ('inout', 'in'))}}}]",
        f"set_input_delay  -clock {pin_clock} -min "
        f"{_num(delays.input_min_ns)} "
        f"[get_ports {{{_targets(group, ('inout', 'in'))}}}]",
        "",
        "# O dado lido é lançado numa borda do relógio do pino e capturado um",
        "# ciclo depois da borda mais próxima do relógio do controlador.",
        f"set clk_mem {{{mem}}}",
        f"set_multicycle_path -setup -end -from [get_clocks {pin_clock}] "
        "-to [get_clocks $clk_mem] 2",
        f"set_multicycle_path -hold  -end -from [get_clocks {pin_clock}] "
        "-to [get_clocks $clk_mem] 1",
        "",
    ]


def _crossing(first: str, second: str, bound: str) -> list[str]:
    """Escreve as quatro exceções de cruzamento entre dois domínios.

    Parameters
    ----------
    first : str
        Expressão do primeiro conjunto de relógios.
    second : str
        Expressão do segundo conjunto.
    bound : str
        Limite em nanossegundos.

    Returns
    -------
    list of str
        As linhas.
    """
    return [
        f"set_max_delay -from {first} -to {second} {bound}",
        f"set_max_delay -from {second} -to {first} {bound}",
        f"set_min_delay -from {first} -to {second} -{bound}",
        f"set_min_delay -from {second} -to {first} -{bound}",
    ]


def _domains(plan: ClockPlan, pattern: str | None, has_mem: bool) -> list[str]:
    """Escreve os conjuntos de relógios e os cruzamentos entre eles.

    Parameters
    ----------
    plan : ClockPlan
        Os relógios.
    pattern : str or None
        O padrão de nó da família.
    has_mem : bool
        Se há relógio de controlador de dispositivo.

    Returns
    -------
    list of str
        As linhas.
    """
    bound = _num(float(plan.min_period_ns))
    fetch = plan.get("fetch")
    names = ["fetch", "core"] if fetch else ["core"]
    lines = [
        "# Os relógios do núcleo e do controlador só se encontram nas pontes,",
        "# com sincronizadores de dois flip-flops; cada cruzamento é limitado",
        "# por um atraso menor que a latência do sincronizador, sem hold. O",
        f"# limite de {bound} ns é o menor período entre os relógios do SoC.",
    ]
    nodes = {r: f"clk_{r}" for r in names}
    lines.extend(
        f"set {nodes[role]} {{{_node(pattern, plan.index(role))}}}"
        for role in names
    )
    listed = " ".join(f"${nodes[r]}" for r in names)
    lines.append(f"set core_clocks [get_clocks [list {listed}]]")
    if has_mem:
        if plan.get("mem_pin") is None:
            mem = _node(pattern, plan.index("mem"))
            lines.append(f"set clk_mem {{{mem}}}")
        lines.append("set mem_clocks  [get_clocks $clk_mem]")
        lines += _crossing("$mem_clocks", "$core_clocks", bound)
        lines += [
            "",
            "# O relógio da JTAG encontra o do controlador no mestre de",
            "# depuração, do mesmo modo.",
            f"set tck_clocks [get_clocks {JTAG_CLOCK}]",
        ]
        lines += _crossing("$mem_clocks", "$tck_clocks", bound)
    else:
        lines.append(f"set tck_clocks [get_clocks {JTAG_CLOCK}]")
    lines += [
        "",
        "# A UART JTAG encontra o relógio da JTAG no domínio do núcleo.",
    ]
    lines += _crossing("$core_clocks", "$tck_clocks", bound)
    return lines


def _false_paths(ports: tuple[Port, ...]) -> list[str]:
    """Escreve os caminhos falsos das E/S lentas.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.

    Returns
    -------
    list of str
        As linhas.
    """
    free_in = [
        p
        for p in ports
        if p.role in ("reset", "switches", "keys") and not p.alias
    ]
    free_out = [p for p in ports if p.role == "leds"]
    displays = " ".join(
        _targets([p], ("out",)) for p in ports if p.role == "display"
    )
    lines = [
        "",
        "# Reset, chaves, botões, LEDs e displays são lentos e assíncronos",
        "# ao relógio do núcleo, sem requisito de tempo.",
    ]
    lines += [
        f"set_false_path -from [get_ports {{{_targets([p], ('in',))}}}]"
        for p in free_in
    ]
    lines += [
        f"set_false_path -to   [get_ports {{{_targets([p], ('out',))}}}]"
        for p in free_out
    ]
    if displays:
        lines.append(f"set_false_path -to   [get_ports {{{displays}}}]")
    return lines


def render_sdc(
    plan: ClockPlan,
    ports: tuple[Port, ...],
    delays: IoDelays | None,
    pattern: str | None,
) -> str:
    """Escreve o `.sdc`.

    Parameters
    ----------
    plan : ClockPlan
        Os relógios.
    ports : tuple of Port
        As portas do topo.
    delays : IoDelays or None
        Os atrasos do chip de SDRAM; `None` sem SDRAM de dispositivo.
    pattern : str or None
        O `clock_node_pattern` da família.

    Returns
    -------
    str
        O texto do arquivo.

    Raises
    ------
    SdcError
        Se falta o padrão de nó, ou a SDRAM não tem atraso de chip.
    """
    lines = [
        "# Restrições geradas pelo riscv-tools (não edite).",
        f"create_clock -name {plan.reference_signal} -period "
        f"{float(1000 / plan.reference_mhz):.3f} "
        f"[get_ports {plan.reference_signal}]",
        "derive_pll_clocks",
        "derive_clock_uncertainty",
        "",
    ]
    has_mem = plan.get("mem") is not None
    if plan.get("mem_pin") is not None:
        if delays is None:
            raise SdcError("sdram without chip io_timing")
        lines += _memory_section(plan, ports, delays, pattern)
    lines += _domains(plan, pattern, has_mem)
    lines += _false_paths(ports)
    return "\n".join(lines) + "\n"
