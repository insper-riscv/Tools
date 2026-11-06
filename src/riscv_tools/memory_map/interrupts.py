"""The interrupt wiring of a platform: the CLINT and its tick.

A platform that has the machine interrupts lists the `CLINT` (and,
for the external lines, `EXT_IRQ`) among its `peripherals` and says in
`interrupts` how fast its clock is and how fast `mtime` counts:

```yaml
interrupts:
  clock_hz: 50000000   # clock of the domain of the core and the CLINT
  mtime_hz: 1000000    # rate at which the mtime of the CLINT counts
```

The `mtime` of the CLINT is a counter of its own, set by this rate. It
is independent of the CSR `time` of Zicntr, which the core serves.

The VHDL package gets `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES`
(clock cycles per increment of `mtime`, the `tick_cycles` generic of the
CLINT), and the runtime header gets the three registers of the CLINT
and the tick rate for the port of the FreeRTOS.
"""

from typing import Any

from riscv_tools.memory_map.core import (
    Mismatch,
    platform_dict,
    platform_list,
)
from riscv_tools.memory_map.expressions import evaluate

# Byte offsets of the registers inside the 64 KiB window of the CLINT
# (the layout of the CLINT of SiFive that the FreeRTOS port expects).
MSIP_OFFSET = 0x0000
MTIMECMP_OFFSET = 0x4000
MTIME_OFFSET = 0xBFF8

CLINT = "CLINT"


def declared(platform: dict[str, Any]) -> bool:
    """Tell whether the platform has an `interrupts` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when the section is there.
    """
    return bool(platform_dict(platform, "interrupts"))


def _rates(platform: dict[str, Any]) -> tuple[int, int]:
    """Read the clock rate and the tick rate of the section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    tuple of (int, int)
        `clock_hz` and `mtime_hz`.
    """
    section = platform_dict(platform, "interrupts")
    return evaluate(section["clock_hz"]), evaluate(section["mtime_hz"])


def tick_cycles(platform: dict[str, Any]) -> int:
    """Count the clock cycles per increment of `mtime`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    int
        `clock_hz / mtime_hz`.
    """
    clock, mtime = _rates(platform)
    return clock // mtime


def problems(
    platform: dict[str, Any],
    generics: dict[str, bool | int] | None = None,
) -> list[Mismatch]:
    """Check the interrupt section against the rest of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    generics : dict of {str: bool or int}, optional
        The generics of the profile; without them the check of the
        profile is skipped.

    Returns
    -------
    list of Mismatch
        The problems; empty when the section is consistent or absent.
    """
    if not declared(platform):
        return []
    section = platform_dict(platform, "interrupts")
    found = [
        Mismatch("interrupts", "", f"{key} is missing")
        for key in ("clock_hz", "mtime_hz")
        if key not in section
    ]
    if found:
        return found
    clock, mtime = _rates(platform)
    if mtime <= 0 or clock <= 0 or clock % mtime:
        found.append(
            Mismatch(
                "interrupts",
                "",
                f"clock_hz {clock} is not a multiple of mtime_hz {mtime}",
            )
        )
    names = {str(p["name"]) for p in platform_list(platform, "peripherals")}
    if CLINT not in names:
        found.append(
            Mismatch("interrupts", "", f"the peripherals have no {CLINT}")
        )
    return found + _profile_problems(generics)


def _profile_problems(
    generics: dict[str, bool | int] | None,
) -> list[Mismatch]:
    """Check that the profile turns the interrupts on.

    Parameters
    ----------
    generics : dict of {str: bool or int} or None
        The generics of the profile; without the switches (a platform
        with no profile specification) nothing is checked.

    Returns
    -------
    list of Mismatch
        The problems found.
    """
    if generics is None or "has_interrupts" not in generics:
        return []
    if generics["has_interrupts"]:
        return []
    return [
        Mismatch(
            "interrupts",
            "",
            "the profile does not turn on has_interrupts "
            "(extras: [Interrupts])",
        )
    ]


def vhdl_lines(platform: dict[str, Any]) -> str:
    """Write the VHDL constants of the tick of the CLINT.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES`, each preceded by
        a blank line and a comment; empty without `interrupts`.
    """
    if not declared(platform):
        return ""
    clock, mtime = _rates(platform)
    return (
        "\n\t-- Frequência do clock do domínio do núcleo e do CLINT, em Hz.\n"
        f"\tconstant CLOCK_HZ          : positive := {clock};\n"
        "\t-- Frequência com que o mtime do CLINT conta, em Hz; é "
        "independente do CSR time.\n"
        f"\tconstant MTIME_HZ          : positive := {mtime};\n"
        "\t-- Ciclos de clock por incremento do mtime (tick_cycles do "
        "CLINT).\n"
        f"\tconstant CLINT_TICK_CYCLES : positive := {clock // mtime};\n"
    )


def runtime_values(
    platform: dict[str, Any], table: dict[str, int]
) -> dict[str, int]:
    """Compute the macros of the runtime header for the CLINT.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    table : dict of {str: int}
        The symbols of the map.

    Returns
    -------
    dict of {str: int}
        `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` and `RV32_MTIME_HZ`;
        empty without `interrupts`.
    """
    if not declared(platform):
        return {}
    base = table[f"{CLINT}.base"]
    return {
        "RV32_MSIP": base + MSIP_OFFSET,
        "RV32_MTIMECMP": base + MTIMECMP_OFFSET,
        "RV32_MTIME": base + MTIME_OFFSET,
        "RV32_MTIME_HZ": _rates(platform)[1],
    }
