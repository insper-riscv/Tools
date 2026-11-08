"""The interrupt wiring of a platform: the CLINT and its tick.

A platform that has the machine interrupts lists the `CLINT` (and,
for the external lines, `EXT_IRQ`) among its `peripherals` and says in
`interrupts` how fast its clock is and how fast `mtime` counts:

```yaml
interrupts:
  clock_hz: 50000000   # clock of the domain of the core and the CLINT
  mtime_hz: 1000000    # rate at which the mtime of the CLINT counts
```

With `clocks.core` in the platform `clock_hz` is left out: it is the
core clock rounded to a whole number of cycles per tick.

The `mtime` of the CLINT is a counter of its own, set by this rate. It
is independent of the CSR `time` of Zicntr, which the core serves.

A platform with the PLIC lists it among its `peripherals` (with a
`size`, the window the PLIC decodes, at least 0x200008 bytes and a power
of two) and describes it in `interrupts`:

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, id: 7, size: 4M}
interrupts:
  clock_hz: 50000000
  mtime_hz: 1000000
  plic: {priority_bits: 3}
  sources:                 # the ids of the lines wired to the PLIC
    - {name: UART, id: 1}
    - {name: TIMER, id: 2}
```

The VHDL package then also gets `PLIC_N_SOURCES` (the largest source
id), `PLIC_PRIORITY_BITS`, `PLIC_ADDR_WIDTH` (the window in words, as a
power of two) and one `IRQ_<NAME>` per source; the runtime header gets
the registers of the PLIC (`RV32_PLIC_PRIORITY`, `RV32_PLIC_PENDING`,
`RV32_PLIC_ENABLE`, `RV32_PLIC_THRESHOLD`, `RV32_PLIC_CLAIM`) and one
`RV32_IRQ_<NAME>` per source.

The VHDL package gets `CLOCK_HZ`, `MTIME_HZ` and `CLINT_TICK_CYCLES`
(clock cycles per increment of `mtime`, the `tick_cycles` generic of the
CLINT), and the runtime header gets the three registers of the CLINT
and the tick rate for the port of the FreeRTOS.
"""

from typing import Any

from riscv_tools.memory_map import sdram_clock
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
PLIC = "PLIC"

# Byte offsets of the registers of the PLIC (riscv-plic-1.0.0), for the
# context 0.
PLIC_PRIORITY_OFFSET = 0x000000
PLIC_PENDING_OFFSET = 0x001000
PLIC_ENABLE_OFFSET = 0x002000
PLIC_THRESHOLD_OFFSET = 0x200000
PLIC_CLAIM_OFFSET = 0x200004
# Smallest window that holds the registers above, and the most sources.
PLIC_MIN_WINDOW = 0x200008
PLIC_MAX_SOURCES = 1023
PLIC_MAX_PRIORITY_BITS = 32


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


def symbols(platform: dict[str, Any]) -> dict[str, int]:
    """Name the tick of the `interrupts` section for the checks.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: int}
        `INTERRUPTS.tick_cycles` (clock cycles per `mtime` tick); empty
        without the section.
    """
    if not declared(platform):
        return {}
    return {"INTERRUPTS.tick_cycles": tick_cycles(platform)}


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
    mtime = evaluate(section["mtime_hz"])
    if "clock_hz" in section:
        return evaluate(section["clock_hz"]), mtime
    return derived_clock_hz(platform, mtime), mtime


def derived_clock_hz(platform: dict[str, Any], mtime: int) -> int:
    """Round the core clock to a whole number of cycles per tick.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    mtime : int
        The tick rate of `mtime`.

    Returns
    -------
    int
        `round(clocks.core / mtime_hz) * mtime_hz`, or 0 without the
        core clock or with a tick rate that is not positive.
    """
    rate = sdram_clock.core_hz(platform)
    if rate is None or mtime <= 0:
        return 0
    return round(rate / mtime) * mtime


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
    has_core_clock = sdram_clock.core_hz(platform) is not None
    needed = ("mtime_hz",) if has_core_clock else ("clock_hz", "mtime_hz")
    found = [
        Mismatch("interrupts", "", f"{key} is missing")
        for key in needed
        if key not in section
    ]
    if found:
        return found
    found = _clock_problems(platform, section, has_core_clock)
    names = {str(p["name"]) for p in platform_list(platform, "peripherals")}
    if CLINT not in names:
        found.append(
            Mismatch("interrupts", "", f"the peripherals have no {CLINT}")
        )
    return (
        found + _plic_problems(platform, names) + _profile_problems(generics)
    )


def _clock_problems(
    platform: dict[str, Any], section: dict[str, Any], has_core_clock: bool
) -> list[Mismatch]:
    """Check clock_hz against clocks.core and against mtime_hz."""
    found: list[Mismatch] = []
    clock, mtime = _rates(platform)
    if "clock_hz" in section and has_core_clock:
        derived = derived_clock_hz(platform, mtime)
        if derived and clock != derived:
            found.append(
                Mismatch(
                    "interrupts",
                    "",
                    f"clock_hz {clock} is not clocks.core rounded to whole "
                    f"ticks ({derived}); leave clock_hz out",
                )
            )
    if mtime <= 0 or clock <= 0 or clock % mtime:
        found.append(
            Mismatch(
                "interrupts",
                "",
                f"clock_hz {clock} is not a multiple of mtime_hz {mtime}",
            )
        )
    return found


def _plic_problems(
    platform: dict[str, Any], names: set[str]
) -> list[Mismatch]:
    """Check the PLIC window and the list of sources.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    names : set of str
        The names of the peripherals.

    Returns
    -------
    list of Mismatch
        The problems; empty without `sources` and `plic`.
    """
    section = platform_dict(platform, "interrupts")
    if "sources" not in section and "plic" not in section:
        return []
    if PLIC not in names:
        return [Mismatch("interrupts", "", f"the peripherals have no {PLIC}")]
    periph = _plic_peripheral(platform)
    if "size" not in periph:
        return [Mismatch("interrupts", "", f"{PLIC} has no size")]
    return _plic_size_problems(
        evaluate(periph["size"])
    ) + _plic_source_problems(platform)


def _plic_size_problems(size: int) -> list[Mismatch]:
    """Check the PLIC window is a power of two inside its slot."""
    found: list[Mismatch] = []
    if size < PLIC_MIN_WINDOW or size & (size - 1):
        found.append(
            Mismatch(
                "interrupts",
                "",
                f"{PLIC} size {size:#x} is not a power of two of at least "
                f"{PLIC_MIN_WINDOW:#x}",
            )
        )
    if size > 1 << 28:
        found.append(
            Mismatch(
                "interrupts",
                "",
                f"{PLIC} size {size:#x} exceeds the 256 MiB slot",
            )
        )
    return found


def _plic_source_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the PLIC sources and the width of its priorities."""
    found: list[Mismatch] = []
    sources = sources_of(platform)
    ids = [i for _, i in sources]
    if len(set(ids)) != len(ids) or len({n for n, _ in sources}) != len(ids):
        found.append(Mismatch("interrupts", "", "source names or ids repeat"))
    if any(not 1 <= i <= PLIC_MAX_SOURCES for i in ids):
        found.append(
            Mismatch(
                "interrupts",
                "",
                f"a source id is outside 1..{PLIC_MAX_SOURCES}",
            )
        )
    bits = _plic_dict(platform).get("priority_bits", 3)
    if not 1 <= int(bits) <= PLIC_MAX_PRIORITY_BITS:
        found.append(
            Mismatch("interrupts", "", "priority_bits is outside 1..32")
        )
    return found


def _plic_peripheral(platform: dict[str, Any]) -> dict[str, Any]:
    """Return the `peripherals` entry of the PLIC.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: Any}
        The entry named `PLIC`.
    """
    return next(
        p for p in platform_list(platform, "peripherals") if p["name"] == PLIC
    )


def _plic_dict(platform: dict[str, Any]) -> dict[str, Any]:
    """Return the `interrupts.plic` section.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: Any}
        The section; empty without it.
    """
    return dict(platform_dict(platform, "interrupts").get("plic") or {})


def sources_of(platform: dict[str, Any]) -> list[tuple[str, int]]:
    """List the sources wired to the PLIC.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of tuple of (str, int)
        `(NAME, id)` in the order of the file; empty without `sources`.
    """
    raw: list[dict[str, Any]] = (
        platform_dict(platform, "interrupts").get("sources") or []
    )
    return [(str(s["name"]).upper(), int(s["id"])) for s in raw]


def has_plic(platform: dict[str, Any]) -> bool:
    """Tell whether the platform describes a PLIC.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when `interrupts` has `sources` or `plic`.
    """
    section = platform_dict(platform, "interrupts")
    return "sources" in section or "plic" in section


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
    return _clint_lines(clock, mtime) + _plic_lines(platform)


def _plic_lines(platform: dict[str, Any]) -> str:
    """Write the VHDL constants of the PLIC and of its sources.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        The constants; empty without a PLIC in the interrupts.
    """
    if not has_plic(platform):
        return ""
    sources = sources_of(platform)
    words = evaluate(_plic_peripheral(platform)["size"]) // 4
    width = words.bit_length() - 1
    bits = int(_plic_dict(platform).get("priority_bits", 3))
    lines = (
        "\n\t-- Número de fontes do PLIC (o maior identificador de fonte).\n"
        f"\tconstant PLIC_N_SOURCES     : positive := "
        f"{max([i for _, i in sources] or [1])};\n"
        "\t-- Largura da prioridade e do limiar do PLIC, em bits.\n"
        f"\tconstant PLIC_PRIORITY_BITS : positive := {bits};\n"
        "\t-- Largura do endereço de palavra da janela do PLIC.\n"
        f"\tconstant PLIC_ADDR_WIDTH    : positive := {width};\n"
    )
    for name, ident in sources:
        lines += (
            f"\t-- Identificador da fonte {name} no PLIC.\n"
            f"\tconstant IRQ_{name} : positive := {ident};\n"
        )
    return lines


def _clint_lines(clock: int, mtime: int) -> str:
    """Write the VHDL constants of the tick of the CLINT.

    Parameters
    ----------
    clock : int
        The clock rate of the core domain, in Hz.
    mtime : int
        The rate at which `mtime` counts, in Hz.

    Returns
    -------
    str
        The three constants.
    """
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
    values = {
        "RV32_MSIP": base + MSIP_OFFSET,
        "RV32_MTIMECMP": base + MTIMECMP_OFFSET,
        "RV32_MTIME": base + MTIME_OFFSET,
        "RV32_MTIME_HZ": _rates(platform)[1],
    }
    if has_plic(platform):
        plic = evaluate(_plic_peripheral(platform)["base"])
        values |= {
            "RV32_PLIC_PRIORITY": plic + PLIC_PRIORITY_OFFSET,
            "RV32_PLIC_PENDING": plic + PLIC_PENDING_OFFSET,
            "RV32_PLIC_ENABLE": plic + PLIC_ENABLE_OFFSET,
            "RV32_PLIC_THRESHOLD": plic + PLIC_THRESHOLD_OFFSET,
            "RV32_PLIC_CLAIM": plic + PLIC_CLAIM_OFFSET,
        }
        for name, ident in sources_of(platform):
            values[f"RV32_IRQ_{name}"] = ident
    return values
