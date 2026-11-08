"""Escritor do PLL na primitiva `altera_pll` (Cyclone V)."""

from riscv_tools.pll_generator.types import (
    PllSolution,
    RenderedPll,
    format_mhz,
)
from riscv_tools.pll_generator.wrapper import module_head


def _altera_pll_outputs(solution: PllSolution) -> str:
    """Escreve os parâmetros por saída do `altera_pll`.

    Parameters
    ----------
    solution : PllSolution
        Os contadores.

    Returns
    -------
    str
        As linhas de parâmetro.
    """
    lines: list[str] = []
    for out in solution.outputs:
        lines += [
            f"\t\t.output_clock_frequency{out.index}"
            f'("{format_mhz(out.mhz)} MHz"),',
            f'\t\t.phase_shift{out.index}("{out.phase_ps} ps"),',
            f"\t\t.duty_cycle{out.index}(50),",
        ]
    return "\n".join(lines)


def render_altera_pll(
    module: str, solution: PllSolution, _quartus_family: str = ""
) -> RenderedPll:
    """Escreve o PLL na primitiva `altera_pll`.

    Parameters
    ----------
    module : str
        Nome do módulo.
    solution : PllSolution
        Os contadores.
    _quartus_family : str, optional
        A família do Quartus, que o `altera_pll` não precisa.

    Returns
    -------
    RenderedPll
        O módulo Verilog com as portas `refclk`, `rst`, `outclk_<i>` e
        `locked`.
    """
    count = len(solution.outputs)
    ports = "".join(f"\toutput wire outclk_{i},\n" for i in range(count))
    names = ", ".join(f"outclk_{i}" for i in reversed(range(count)))
    notes = "\n".join(
        f"//   outclk_{o.index}  {format_mhz(o.mhz)} MHz, "
        f"fase {o.phase_ps} ps  {o.role}"
        for o in solution.outputs
    )
    vco = format_mhz(solution.vco_mhz)
    text = f"""// PLL gerado pelo riscv-tools (não edite): VCO de {vco} MHz
// a partir de {format_mhz(solution.reference_mhz)} MHz.
//
{module_head(notes, module, ports)}
\taltera_pll #(
\t\t.fractional_vco_multiplier("false"),
\t\t.reference_clock_frequency("{format_mhz(solution.reference_mhz)} MHz"),
\t\t.operation_mode("direct"),
\t\t.number_of_clocks({count}),
{_altera_pll_outputs(solution)}
\t\t.pll_type("General"),
\t\t.pll_subtype("General")
\t) altera_pll_i (
\t\t.rst\t(rst),
\t\t.outclk\t({{{names}}}),
\t\t.locked\t(locked),
\t\t.fboutclk\t( ),
\t\t.fbclk\t(1'b0),
\t\t.refclk\t(refclk)
\t);

endmodule
"""
    assign = "set_instance_assignment -name"
    target = f'"*{module}*|altera_pll:altera_pll_i*|*"'
    return RenderedPll(
        module,
        ".v",
        text,
        (
            f"{assign} PLL_COMPENSATION_MODE DIRECT -to {target}",
            f"{assign} PLL_AUTO_RESET OFF -to {target}",
            f"{assign} PLL_BANDWIDTH_PRESET AUTO -to {target}",
        ),
    )
