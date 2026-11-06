"""The clock of the SDRAM controller of a platform.

A platform with an SDRAM says in `sdram` how fast the controller runs
and how far the pin `DRAM_CLK` is shifted from it:

```yaml
sdram:
  clock_hz: 100000000      # controller clock (PLL output 0)
  dram_clk_phase_ps: 4000  # phase of DRAM_CLK against it (PLL output 1)
```

The optional `pll` section holds the phase of the core clock (PLL output
3) in `core_phase_ps`, which only the checks use (`PLL.core_phase_ps`).

The VHDL package gets `SDRAM_CLOCK_HZ` and `SDRAM_TCK_PS` (the period
the controller and the chip model convert the chip timings with), and
the checks of the platform can name `SDRAM.clock_mhz` and
`SDRAM.dram_clk_phase_ps` to keep the PLL file in step with the map.
"""

from typing import Any

from riscv_tools.memory_map.core import Mismatch, platform_dict
from riscv_tools.memory_map.expressions import evaluate

PS_PER_S = 1_000_000_000_000
HZ_PER_MHZ = 1_000_000


def declared(platform: dict[str, Any]) -> bool:
    """Tell whether the platform has an `sdram` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when the section is there.
    """
    return bool(platform_dict(platform, "sdram"))


def problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the `sdram` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        The problems; empty when the section is consistent or absent.
    """
    if not declared(platform):
        return []
    section = platform_dict(platform, "sdram")
    found = [
        Mismatch("sdram", "", f"{key} is missing")
        for key in ("clock_hz", "dram_clk_phase_ps")
        if key not in section
    ]
    if found:
        return found
    clock = evaluate(section["clock_hz"])
    if clock <= 0 or PS_PER_S % clock:
        found.append(
            Mismatch(
                "sdram", "", f"clock_hz {clock} has no whole period in ps"
            )
        )
    elif not 0 <= evaluate(section["dram_clk_phase_ps"]) < PS_PER_S // clock:
        found.append(
            Mismatch("sdram", "", "dram_clk_phase_ps is not inside one period")
        )
    return found


def symbols(platform: dict[str, Any]) -> dict[str, int]:
    """Name the values of the section for the checks.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: int}
        `SDRAM.clock_mhz`, `SDRAM.tck_ps` and `SDRAM.dram_clk_phase_ps`
        (with the `sdram` section) and `PLL.core_phase_ps` (with the
        `pll` section).
    """
    out: dict[str, int] = {}
    pll = platform_dict(platform, "pll")
    if "core_phase_ps" in pll:
        out["PLL.core_phase_ps"] = evaluate(pll["core_phase_ps"])
    if not declared(platform):
        return out
    section = platform_dict(platform, "sdram")
    clock = evaluate(section["clock_hz"])
    return out | {
        "SDRAM.clock_mhz": clock // HZ_PER_MHZ,
        "SDRAM.tck_ps": PS_PER_S // clock,
        "SDRAM.dram_clk_phase_ps": evaluate(section["dram_clk_phase_ps"]),
    }


def vhdl_lines(platform: dict[str, Any]) -> str:
    """Write the VHDL constants of the controller clock.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        `SDRAM_CLOCK_HZ` and `SDRAM_TCK_PS`, each preceded by a comment;
        empty without the section.
    """
    if not declared(platform):
        return ""
    clock = evaluate(platform_dict(platform, "sdram")["clock_hz"])
    return (
        "\n\t-- Frequência do clock do controlador da SDRAM, em Hz.\n"
        f"\tconstant SDRAM_CLOCK_HZ : positive := {clock};\n"
        "\t-- Período desse clock, em picossegundos: a base da conversão dos "
        "tempos do chip em ciclos.\n"
        f"\tconstant SDRAM_TCK_PS   : positive := {PS_PER_S // clock};\n"
    )
