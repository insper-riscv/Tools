"""Refuse the cores and boot memories the toolchain cannot serve.

Each rule is a problem of the platform, found before any file is
generated and by `check-memory-map`, with what to do in the message.

1. `V-B1`: the BOOT_MEMORY size is not a power of two.
2. `V-B2`: `boot.wait_restart` leaves no room in the BOOT_MEMORY for
   the wait loop.
3. `V-I2`: the platform has an instruction cache or an instruction
   memory on the bus, and `core.extensions` has no `Zifencei`. Without
   `fence.i` the fetch keeps a stale copy of what the boot wrote.

A platform without either of them does not need `Zifencei`: `fence.i`
has no effect there, so the extension is not required. A data cache
alone does not count, because it never holds code the fetch reads (the
instructions come from a memory the data side does not reach), and
`fence.i` then only flushes data.

The image has the RV64 multilibs (`rv64i/lp64` and the others), so a
64-bit core is not refused. The extension `Q` is refused when the `core`
block is read (see `core_profile`), because no compiler of the image can
generate it.
"""

from typing import Any, cast

from riscv_tools.memory_map import memory as memory_choice
from riscv_tools.memory_map.core import Mismatch, platform_dict, platform_list
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.march import extension_names, platform_core

# Bytes que o laço de espera ocupa a partir de `wait_restart`: carregar
# o fim da RAM (lui e addi), ler o `fromhost`, desviar e saltar.
WAIT_LOOP_BYTES = 20


def _problem(detail: str) -> Mismatch:
    """Wrap a message as a problem of the platform.

    Parameters
    ----------
    detail : str
        What is wrong and what to do.

    Returns
    -------
    Mismatch
        The problem.
    """
    return Mismatch("platform", "", detail)


def boot_size_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the size of the BOOT_MEMORY (V-B1, V-B2).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform; the first region is the BOOT_MEMORY.

    Returns
    -------
    list of Mismatch
        V-B1 when the size is not a power of two, and V-B2 when
        `boot.wait_restart` is inside the memory but leaves less than
        the wait loop after it.
    """
    regions = platform_list(platform, "regions")
    if not regions:
        return []
    name = str(regions[0]["name"])
    size = evaluate(regions[0]["size"])
    found: list[Mismatch] = []
    if size <= 0 or size & (size - 1):
        found.append(
            _problem(
                f"V-B1 {name} size {size} bytes is not a power of two; "
                "set memory.boot.size to 2K, 4K, 8K, ..."
            )
        )
    boot = platform_dict(platform, "boot")
    if "wait_restart" not in boot:
        return found
    wait = evaluate(boot["wait_restart"])
    if wait < size < wait + WAIT_LOOP_BYTES:
        found.append(
            _problem(
                f"V-B2 {name} ({size} bytes) ends {size - wait} bytes "
                f"after boot.wait_restart 0x{wait:X}, and the wait loop "
                f"needs {WAIT_LOOP_BYTES}; grow memory.boot.size or lower "
                "boot.wait_restart"
            )
        )
    return found


def fetch_sources(platform: dict[str, Any]) -> list[str]:
    """Name what keeps the instruction fetch away from the memory.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of str
        The instruction cache, the instruction memory on the bus and
        the RAM that the fetch reaches, for the ones the platform has;
        empty without a `memory` choice or with an invalid one.
    """
    memory, invalid = memory_choice.read(platform)
    if memory is None or invalid:
        return []
    found: list[str] = []
    if memory.has_icache:
        found.append("an instruction cache")
    if memory.rom_external:
        found.append("the instruction memory on the bus")
    section = cast(dict[str, Any], platform.get("memory") or {})
    ram = section.get("ram")
    if isinstance(ram, dict) and cast(dict[str, Any], ram).get("fetch"):
        found.append("a RAM that the instruction fetch reaches")
    return found


def zifencei_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check that the platform has the `Zifencei` it needs (V-I2).

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        V-I2 when the instruction fetch can see a copy of the code
        (see `fetch_sources`) and the core has no `Zifencei`; empty
        when the platform has neither, because `fence.i` then has no
        effect and the extension is not required.
    """
    sources = fetch_sources(platform)
    if not sources:
        return []
    # Um nome de perfil inválido é problema de quem lê o perfil.
    try:
        has_zifencei = "zifencei" in extension_names(platform_core(platform))
    except ValueError:
        return []
    if has_zifencei:
        return []
    return [
        _problem(
            f"V-I2 the platform has {' and '.join(sources)}, so the "
            "instruction fetch can keep a copy of the code older than "
            "what the boot wrote, and only fence.i (the extension "
            "Zifencei) makes the fetch see it; add Zifencei to "
            "core.extensions, or remove the cache and the instruction "
            "memory on the bus"
        )
    ]


def core_problems(
    platform: dict[str, Any],
) -> list[Mismatch]:
    """Check the core against what the toolchain and the memories need.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        V-I2 when the platform needs `Zifencei` and the core lacks it.
    """
    return zifencei_problems(platform)


def problems(
    platform: dict[str, Any],
    xlen: int | None = None,
) -> list[Mismatch]:
    """Gather the problems of the BOOT_MEMORY and of the core.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    xlen : int, optional
        Given for a variant of the `config_pkg` (see `config_pkg`),
        which a formal proof may make 64 bits wide or without
        `Zifencei` on purpose; the rule of the core (V-I2) is
        then skipped, because no program is built for a variant.

    Returns
    -------
    list of Mismatch
        The problems; empty when the platform is served.
    """
    found = boot_size_problems(platform)
    if xlen is None:
        found += core_problems(platform)
    return found
