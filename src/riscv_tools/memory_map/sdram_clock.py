"""The clocks of a platform that the memory map converts with.

A platform says in `clocks` how fast its clocks run (the PLL, the
`.sdc` and the VHDL package are all generated from this one place):

```yaml
clocks:
  core: {mhz: 76.923077, phase_ps: 7500}  # clock of the core
  mem:  {mhz: 100}                        # SDRAM controller
```

The VHDL package gets `SDRAM_CLOCK_HZ` and `SDRAM_TCK_PS` (the
period the controller and the chip model convert the chip timings
with) from `clocks.mem`, and the checks of the platform can name
`CLOCKS.mem_mhz`, `CLOCKS.mem_tck_ps`, `CLOCKS.core_mhz` and
`CLOCKS.core_phase_ps`.
The phase of the pin clock `DRAM_CLK` belongs to the board, not to the
platform (`memories.sdram.clk_phase_ps` of the `board.yaml`).
"""

from fractions import Fraction
from typing import Any, cast

from riscv_tools.memory_map.core import Mismatch, platform_dict

PS_PER_S = 1_000_000_000_000
HZ_PER_MHZ = 1_000_000


def _mhz(platform: dict[str, Any], clock: str) -> Fraction | None:
    """Read the frequency of one clock of the `clocks` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    clock : str
        `core`, `fetch` or `mem`.

    Returns
    -------
    Fraction or None
        The frequency in MHz, or None when the clock is not declared or
        is not a number.
    """
    entry = platform_dict(platform, "clocks").get(clock)
    if not isinstance(entry, dict) or "mhz" not in entry:
        return None
    fields = cast(dict[str, Any], entry)
    try:
        return Fraction(str(fields["mhz"]))
    except ValueError, ZeroDivisionError:
        return None


def declared(platform: dict[str, Any]) -> bool:
    """Tell whether the platform has a `clocks.mem` clock.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when the controller clock is there.
    """
    return "mem" in platform_dict(platform, "clocks")


def core_hz(platform: dict[str, Any]) -> Fraction | None:
    """Give the frequency of the core clock in hertz.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    Fraction or None
        `clocks.core.mhz` in Hz, or None without the clock.
    """
    mhz = _mhz(platform, "core")
    return None if mhz is None else mhz * HZ_PER_MHZ


def problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the `clocks` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        The problems; empty when the section is consistent or absent.
    """
    found: list[Mismatch] = []
    for name in platform_dict(platform, "clocks"):
        mhz = _mhz(platform, name)
        if mhz is None or mhz <= 0:
            found.append(
                Mismatch(
                    "clocks", "", f"{name}.mhz is missing or not positive"
                )
            )
    if found or not declared(platform):
        return found
    clock = (_mhz(platform, "mem") or Fraction(1)) * HZ_PER_MHZ
    if clock.denominator != 1 or PS_PER_S % int(clock):
        found.append(
            Mismatch("clocks", "", f"mem {clock} Hz has no whole period in ps")
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
        `CLOCKS.mem_mhz` and `CLOCKS.mem_tck_ps` (with `clocks.mem`),
        `CLOCKS.core_mhz` (rounded) and `CLOCKS.core_phase_ps` (with
        `clocks.core`).
    """
    out: dict[str, int] = {}
    core = platform_dict(platform, "clocks").get("core")
    if isinstance(core, dict) and "phase_ps" in core:
        out["CLOCKS.core_phase_ps"] = int(
            cast(dict[str, Any], core)["phase_ps"]
        )
    core_rate = core_hz(platform)
    if core_rate is not None:
        out["CLOCKS.core_mhz"] = round(core_rate / HZ_PER_MHZ)
    if declared(platform):
        clock = int((_mhz(platform, "mem") or Fraction(0)) * HZ_PER_MHZ)
        out["CLOCKS.mem_mhz"] = clock // HZ_PER_MHZ
        out["CLOCKS.mem_tck_ps"] = PS_PER_S // clock
    return out


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
        empty without `clocks.mem`.
    """
    if not declared(platform):
        return ""
    clock = int((_mhz(platform, "mem") or Fraction(0)) * HZ_PER_MHZ)
    return (
        "\n\t-- Frequência do clock do controlador da SDRAM, em Hz.\n"
        f"\tconstant SDRAM_CLOCK_HZ : positive := {clock};\n"
        "\t-- Período desse clock, em picossegundos: a base da conversão dos "
        "tempos do chip em ciclos.\n"
        f"\tconstant SDRAM_TCK_PS   : positive := {PS_PER_S // clock};\n"
    )
