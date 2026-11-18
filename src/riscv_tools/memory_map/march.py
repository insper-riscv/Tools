"""The `-march`, the `-mabi` and the multilib of a core.

The `core` block of a platform (`type`, `base` and `extensions`, the
extras included) decides how a program is compiled for it. This module
turns the block into the `-march` and the `-mabi` of the GCC and says
which multilib of the picolibc those two pick.

The `-march` is built in this order:

1. `rv32i` or `rv32e` (`rv64i` and `rv64e` for 64 bits), with an `m`
   when the core has `M`.
2. `Zicclsm`, `Zicsr`, `Zicntr`, `Zihpm`, `Zifencei`, `Zimop`,
   `Zicond` and `Zmmul`, each as `_<name>`, in the order of the profile
   matrix of the Core. `Zicntr` and `Zihpm` also write `_zicsr`, which
   the GCC wants explicit.
3. `Zihintntl` and `Zihintpause`, which the GCC accepts.

`Interrupts`, `Sscofpmf` and `AccessFaults` are not ISA, so they stay
out. The `-mabi` is `ilp32` for the base I and `ilp32e` for the base E
(`lp64` and `lp64e` for 64 bits).

Only the base and the multiplication choose the multilib, so six
libraries cover every profile: `rv32i`, `rv32i_zmmul` and `rv32im` for
the base I, `rv32e`, `rv32e_zmmul` and `rv32em_zmmul` for the base E.
The image has no RV64 multilib, so the multilib of a 64-bit core is an
error, and so is the whole platform (see `core_checks`).
"""

from typing import Any, cast

from riscv_tools.memory_map.core_profile import (
    IMPLYING_ZICSR,
    NAME_ORDER,
    legacy_to_core,
)
from riscv_tools.memory_map.profile import profile_name

# Extensões que o GCC aceita e que não mudam a biblioteca.
MARCH_EXTRAS = ("Zihintntl", "Zihintpause")
RV32 = 32
RV64 = 64
NO_RV64_MULTILIB = (
    "core.type 64 has no multilib in the toolchain image (the compiler "
    "accepts rv64 and links with the 32-bit libraries without a "
    "warning); use core.type 32"
)
# -march que o GCC da imagem assume quando o programa não dá nenhum.
DEFAULT_MARCH = "rv32i"


def extension_names(core: dict[str, Any]) -> set[str]:
    """Collect the lower-case names of the extensions of a block.

    Parameters
    ----------
    core : dict of {str: Any}
        The `core` block.

    Returns
    -------
    set of str
        The names of `extensions`, with the `Zicsr` that `Zicntr` and
        `Zihpm` imply.
    """
    listed = cast("list[Any]", core.get("extensions") or [])
    names = {str(item).lower() for item in listed}
    if names & {name.lower() for name in IMPLYING_ZICSR}:
        names.add("zicsr")
    return names


def _width(core: dict[str, Any]) -> tuple[int, str]:
    """Read the width and the base letter of a block.

    Parameters
    ----------
    core : dict of {str: Any}
        The `core` block.

    Returns
    -------
    tuple of (int, str)
        32 or 64, and `i` or `e`.
    """
    return int(core["type"]), str(core["base"]).lower()


def march_of(core: dict[str, Any]) -> str:
    """Write the `-march` of a core.

    Parameters
    ----------
    core : dict of {str: Any}
        The `core` block: `type`, `base` and `extensions`, with the
        extras in the list.

    Returns
    -------
    str
        The `-march` value, such as `rv32im_zicsr_zicntr`.
    """
    kind, base = _width(core)
    names = extension_names(core)
    head = f"rv{kind}{base}" + ("m" if "m" in names else "")
    parts = [name.lower() for name in NAME_ORDER if name.lower() in names]
    parts += [name.lower() for name in MARCH_EXTRAS if name.lower() in names]
    return "_".join([head, *parts])


def abi_of(core: dict[str, Any]) -> str:
    """Write the `-mabi` of a core.

    Parameters
    ----------
    core : dict of {str: Any}
        The `core` block.

    Returns
    -------
    str
        `ilp32` or `ilp32e` for 32 bits, `lp64` or `lp64e` for 64.
    """
    kind, base = _width(core)
    prefix = "ilp32" if kind == RV32 else "lp64"
    return prefix + ("e" if base == "e" else "")


def multilib_of(core: dict[str, Any]) -> str:
    """Name the multilib of the picolibc that a core links with.

    Parameters
    ----------
    core : dict of {str: Any}
        The `core` block.

    Returns
    -------
    str
        The directory as `-print-multi-directory` writes it, such as
        `rv32i_zmmul/ilp32`. The variant of the default `-march` of the
        image, `rv32i`, is the root `.`, and `M` takes the `_zmmul`
        variant, as the compiler picks it.

    Raises
    ------
    ValueError
        If the block is 64 bits wide, which has no multilib.
    """
    kind, base = _width(core)
    if kind == RV64:
        raise ValueError(NO_RV64_MULTILIB)
    names = extension_names(core)
    letter = "m" if "m" in names else ""
    # A multiplicação M usa a biblioteca `_zmmul`, a mesma do Zmmul.
    zmmul = "zmmul" in names or bool(letter)
    variant = f"rv{kind}{base}{letter}" + ("_zmmul" if zmmul else "")
    if variant == f"rv{kind}i":
        return "."
    return f"{variant}/{abi_of(core)}"


def platform_core(platform: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the `core` block of a loaded platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform, whose `profile` (or the `--profile`
        override) and `extras` the `core` block derived.

    Returns
    -------
    dict of {str: Any}
        `type`, `base` and `extensions`, the extras included.
    """
    extras = [str(e) for e in cast("list[Any]", platform.get("extras") or [])]
    return legacy_to_core(profile_name(platform), extras)


_SELF_SPEC = "\n*self_spec:\n"


def add_self_spec(text: str, core: dict[str, Any], default_march: str) -> str:
    """Give a program the `-march` of the core in a specs file.

    GCC puts its own default `-march` on the command line before any
    spec file is read, so a spec cannot tell a missing option from the
    default. The rule replaces `-march` and `-mabi` only when `-march`
    is the default of the toolchain, which is what a program compiled
    without it carries; any other `-march` is kept.

    Parameters
    ----------
    text : str
        The specs file. When it already has a `*self_spec` (the one of
        C++, see `cxx`), the rule goes at the end of that line, so the
        file keeps a single section.
    core : dict of {str: Any}
        The `core` block.
    default_march : str
        The `-march` the toolchain assumes without one.

    Returns
    -------
    str
        The file with the rule.
    """
    rule = (
        f"%{{march={default_march}:%<march=* %<mabi=*"
        f" -march={march_of(core)} -mabi={abi_of(core)}}}"
    )
    if _SELF_SPEC not in text:
        return f"{text}{_SELF_SPEC}{rule}\n"
    head, tail = text.split(_SELF_SPEC, 1)
    line, rest = tail.split("\n", 1)
    return f"{head}{_SELF_SPEC}{line} {rule}\n{rest}"
