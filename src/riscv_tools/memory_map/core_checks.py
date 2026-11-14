"""Refuse the cores and boot memories the toolchain cannot serve.

Each rule is a problem of the platform, found before any file is
generated and by `check-memory-map`, with what to do in the message.

1. `V-B1`: the BOOT_MEMORY size is not a power of two.
2. `V-B2`: `boot.wait_restart` leaves no room in the BOOT_MEMORY for
   the wait loop.
3. `V-I1`: `core.type` is 64. The compiler accepts `rv64` and links
   with the 32-bit libraries without a warning, because the toolchain
   image has no RV64 multilib.
4. `V-I2`: a cache (instruction or data) without `Zifencei`. The
   `fence.i` is what makes the caches drop their lines.

The extension `Q` is refused when the `core` block is read (see
`core_profile`), because no compiler of the image can generate it.
"""

from contextlib import suppress
from typing import Any

from riscv_tools.memory_map import memory
from riscv_tools.memory_map.boot_config import flags_of
from riscv_tools.memory_map.core import Mismatch, platform_dict, platform_list
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.march import (
    NO_RV64_MULTILIB,
    RV64,
    platform_core,
)
from riscv_tools.memory_map.profile import xlen_of

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


def core_problems(
    platform: dict[str, Any],
) -> list[Mismatch]:
    """Check the core against what the toolchain and the caches need.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        V-I1 for a 64-bit core and V-I2 for a cache without Zifencei.
    """
    found: list[Mismatch] = []
    # Um nome de perfil inválido é problema de quem lê o perfil.
    with suppress(ValueError):
        if xlen_of(platform) == RV64:
            found.append(_problem(f"V-I1 {NO_RV64_MULTILIB}"))
    choice = memory.read(platform)[0]
    if choice is None:
        return found
    caches = [
        name
        for name, present in (
            ("icache", choice.has_icache),
            ("dcache", choice.has_dcache),
        )
        if present
    ]
    if caches and not flags_of(platform_core(platform))["Zifencei"]:
        found.append(
            _problem(
                f"V-I2 the platform has {' and '.join(caches)} but the "
                "core lacks Zifencei, whose fence.i makes the caches drop "
                "their lines; add Zifencei to core.extensions"
            )
        )
    return found


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
        `Zifencei` on purpose; the rules of the core (V-I1, V-I2) are
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
