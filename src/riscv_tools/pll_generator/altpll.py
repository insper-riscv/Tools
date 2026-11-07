"""Escritor do PLL na primitiva `altpll` (Cyclone IV E, MAX 10, C10 LP).

O texto segue o projeto mínimo medido na tarefa M.0.2, que sintetiza
nas quatro famílias. O `altpll` descreve cada saída pela razão
$f_{saida} / f_{entrada}$ (multiplicador e divisor) e pela fase em
picossegundos.
"""

from fractions import Fraction

from riscv_tools.pll_generator.types import (
    PllSolution,
    RenderedPll,
    format_mhz,
)

# O `altpll` tem até cinco saídas de relógio nestas famílias.
WIDTH_CLOCK = 5
_PS_PER_US = 1_000_000
# Portas do componente que o projeto não usa, com o valor que as prende.
_IDLE_PORTS = (
    "activeclock",
    "clkbad0",
    "clkbad1",
    "clkloss",
    "clkswitch",
    "configupdate",
    "fbin",
    "inclk1",
    "pfdena",
    "phasecounterselect",
    "phasedone",
    "phasestep",
    "phaseupdown",
    "pllena",
    "scanaclr",
    "scanclk",
    "scanclkena",
    "scandata",
    "scandataout",
    "scandone",
    "scanread",
    "scanwrite",
)
_IDLE_CONNECTIONS = (
    ".activeclock (),",
    ".clkbad (),",
    ".clkena ({6{1'b1}}),",
    ".clkloss (),",
    ".clkswitch (1'b0),",
    ".configupdate (1'b0),",
    ".enable0 (),",
    ".enable1 (),",
    ".extclk (),",
    ".extclkena ({4{1'b1}}),",
    ".fbin (1'b1),",
    ".fbmimicbidir (),",
    ".fbout (),",
    ".fref (),",
    ".icdrclk (),",
    ".pfdena (1'b1),",
    ".phasecounterselect ({4{1'b1}}),",
    ".phasedone (),",
    ".phasestep (1'b1),",
    ".phaseupdown (1'b1),",
    ".pllena (1'b1),",
    ".scanaclr (1'b0),",
    ".scanclk (1'b0),",
    ".scanclkena (1'b1),",
    ".scandata (1'b0),",
    ".scandataout (),",
    ".scandone (),",
    ".scanread (1'b0),",
    ".scanwrite (1'b0),",
    ".sclkout0 (),",
    ".sclkout1 (),",
    ".vcooverrange (),",
    ".vcounderrange ()",
)


def _ratio(out: Fraction, reference: Fraction) -> tuple[int, int]:
    """Dá o multiplicador e o divisor de uma saída.

    Parameters
    ----------
    out : Fraction
        Frequência da saída.
    reference : Fraction
        Frequência de entrada.

    Returns
    -------
    tuple of (int, int)
        Multiplicador e divisor da razão irredutível.
    """
    ratio = out / reference
    return ratio.numerator, ratio.denominator


def _output_parameters(solution: PllSolution) -> list[str]:
    """Escreve os parâmetros de cada saída usada.

    Parameters
    ----------
    solution : PllSolution
        Os contadores.

    Returns
    -------
    list of str
        Divisor, duty cycle, multiplicador e fase de cada saída.
    """
    lines: list[str] = []
    for out in solution.outputs:
        mult, div = _ratio(out.mhz, solution.reference_mhz)
        lines += [
            f"\t\t.clk{out.index}_divide_by({div}),",
            f"\t\t.clk{out.index}_duty_cycle(50),",
            f"\t\t.clk{out.index}_multiply_by({mult}),",
            f'\t\t.clk{out.index}_phase_shift("{out.phase_ps}"),',
        ]
    return lines


def _port_parameters(used: int) -> list[str]:
    """Escreve os parâmetros `port_*` do componente.

    Parameters
    ----------
    used : int
        Quantas saídas de relógio o projeto usa.

    Returns
    -------
    list of str
        `PORT_USED` para o que o projeto liga, `PORT_UNUSED` no resto.
    """
    lines = [
        '\t\t.port_areset("PORT_USED"),',
        '\t\t.port_inclk0("PORT_USED"),',
        '\t\t.port_locked("PORT_USED"),',
    ]
    lines += [f'\t\t.port_{p}("PORT_UNUSED"),' for p in _IDLE_PORTS]
    lines += [
        f'\t\t.port_clk{i}("PORT_{"USED" if i < used else "UNUSED"}"),'
        for i in range(6)
    ]
    lines += [f'\t\t.port_clkena{i}("PORT_UNUSED"),' for i in range(6)]
    return lines


def render_altpll(
    module: str, solution: PllSolution, quartus_family: str
) -> RenderedPll:
    """Escreve o PLL na primitiva `altpll`.

    Parameters
    ----------
    module : str
        Nome do módulo.
    solution : PllSolution
        Os contadores.
    quartus_family : str
        A família do Quartus (`Cyclone IV E`).

    Returns
    -------
    RenderedPll
        O módulo Verilog com as portas `refclk`, `rst`, `outclk_<i>` e
        `locked`, com a instância interna `altpll_component`.
    """
    count = len(solution.outputs)
    ports = "".join(f"\toutput wire outclk_{i},\n" for i in range(count))
    assigns = "\n".join(
        f"\tassign outclk_{i} = clk_bus[{i}];" for i in range(count)
    )
    period_ps = round(_PS_PER_US / solution.reference_mhz)
    notes = "\n".join(
        f"//   outclk_{o.index}  {format_mhz(o.mhz)} MHz, fase {o.phase_ps} ps"
        f"  {o.role}"
        for o in solution.outputs
    )
    parameters = [
        '\t\t.bandwidth_type("AUTO"),',
        *_output_parameters(solution),
        '\t\t.compensation_mode("NORMAL"),',
        f"\t\t.inclk0_input_frequency({period_ps}),",
        f'\t\t.intended_device_family("{quartus_family}"),',
        '\t\t.lpm_type("altpll"),',
        '\t\t.operation_mode("NORMAL"),',
        '\t\t.pll_type("AUTO"),',
        *_port_parameters(count),
        '\t\t.self_reset_on_loss_lock("OFF"),',
        f"\t\t.width_clock({WIDTH_CLOCK})",
    ]
    connections = [
        "\t\t.areset (rst),",
        "\t\t.inclk  ({1'b0, refclk}),",
        "\t\t.clk    (clk_bus),",
        "\t\t.locked (locked),",
        *(f"\t\t{c}" for c in _IDLE_CONNECTIONS),
    ]
    ref = format_mhz(solution.reference_mhz)
    text = f"""// PLL gerado pelo riscv-tools (não edite): altpll da família
// {quartus_family}, entrada de {ref} MHz.
//
{notes}
`timescale 1ns/10ps
module {module} (
\tinput  wire refclk,
\tinput  wire rst,
{ports}\toutput wire locked
);

\twire [{WIDTH_CLOCK - 1}:0] clk_bus;
{assigns}

\taltpll #(
{chr(10).join(parameters)}
\t) altpll_component (
{chr(10).join(connections)}
\t);

endmodule
"""
    return RenderedPll(module, ".v", text, ())
