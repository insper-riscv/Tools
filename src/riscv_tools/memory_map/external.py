"""The external peripherals of a platform: those of `Peripherals`.

An entry of `peripherals` whose `kind` is one of `kinds.EXTERNAL` is a
peripheral that the generated top of the board instantiates next to the
SoC and wires to the pins of a role of the board:

```yaml
peripherals:
  KBD:
    kind: ps2
    device: keyboard         # or mouse
    base: 0x80007000
  MOUSE:
    kind: ps2
    device: mouse
    base: 0x80007100
  SD:
    kind: sd_spi
    base: 0x80008000
    need: optional           # omitted, with a warning, if no pins
```

`size` is optional and defaults to the registers of the entity (the
word address bits it decodes). `instance` picks the instance of the
board role, and by default each peripheral of a role takes the next
one, in the order of `peripherals`. `need: optional` lets the board
lack the role: the peripheral is then left out of the top.

An entity with an interrupt line gets a source of the PLIC like a
timer does (see `riscv_tools.memory_map.timers`).
"""

from typing import Any

from riscv_tools.memory_map import kinds
from riscv_tools.memory_map.core import (
    Mismatch,
    peripheral_list,
    platform_dict,
)
from riscv_tools.memory_map.kinds import ExternalKind, external_of
from riscv_tools.memory_map.timers import FIXED_LINES, table, timer_list


def external_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """List the external peripherals, in the order of `peripherals`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of dict of {str: Any}
        The completed entries (see `peripheral_list`) of the external
        kinds.
    """
    return [
        item
        for item in peripheral_list(platform)
        if external_of(item) is not None
    ]


def line_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """List the peripherals that take a line of the PLIC by default.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of dict of {str: Any}
        The timers and the external peripherals whose entity has an
        interrupt line, in the order of `peripherals`.
    """
    timers = {str(item["name"]) for item in timer_list(platform)}
    return [
        item
        for item in peripheral_list(platform)
        if str(item["name"]) in timers or _has_irq(item)
    ]


def _has_irq(item: dict[str, Any]) -> bool:
    """Tell whether an external peripheral has an interrupt line.

    Parameters
    ----------
    item : dict of {str: Any}
        An external peripheral.

    Returns
    -------
    bool
        True when the kind has one.
    """
    kind = external_of(item)
    return kind is not None and kind.irq


def instances(platform: dict[str, Any]) -> dict[str, int]:
    """Give the instance of the board role each peripheral uses.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    dict of {str: int}
        By name, `instance` when written, else the least number of the
        role that no earlier peripheral of the role took.
    """
    taken: dict[str, set[int]] = {}
    found: dict[str, int] = {}
    items = external_list(platform)
    for item in items:
        kind = kinds.EXTERNAL[str(item["kind"])]
        if "instance" in item:
            taken.setdefault(kind.role, set()).add(int(item["instance"]))
    for item in items:
        kind = kinds.EXTERNAL[str(item["kind"])]
        used = taken.setdefault(kind.role, set())
        if "instance" in item:
            found[str(item["name"])] = int(item["instance"])
            continue
        number = 0
        while number in used:
            number += 1
        used.add(number)
        found[str(item["name"])] = number
    return found


def _problem(code: str, name: str, detail: str) -> Mismatch:
    """Write one problem of an external peripheral."""
    return Mismatch("platform", "", f"{code} peripheral {name}: {detail}")


def _variant_problems(
    item: dict[str, Any], kind: ExternalKind
) -> list[Mismatch]:
    """Check the field that picks the entity and the window."""
    name = str(item["name"])
    variant = kind.variant(item)
    field_name = kind.variant_field
    if variant is None:
        found = [] if field_name not in item else list(kind.variants)
        detail = (
            f"`{field_name}` is required, one of {list(kind.variants)}"
            if field_name not in item
            else f"`{field_name}` must be one of {found}"
        )
        return [_problem("V-P12", name, detail)]
    if int(item.get("size", 0)) < variant.window:
        return [
            _problem(
                "V-P11",
                name,
                f"{kind.name} needs `size` of at least {variant.window} "
                f"bytes, the registers of {variant.entity}",
            )
        ]
    return []


def _instance_problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check that no two peripherals take one instance of a role."""
    seen: dict[tuple[str, int], str] = {}
    found: list[Mismatch] = []
    for name, number in instances(platform).items():
        role = _role_of(platform, name)
        if (role, number) in seen:
            found.append(
                _problem(
                    "V-P13",
                    name,
                    f"instance {number} of the role {role} is also taken "
                    f"by {seen[(role, number)]}",
                )
            )
        seen[(role, number)] = name
    return found


def _role_of(platform: dict[str, Any], name: str) -> str:
    """Give the board role of an external peripheral by name."""
    for item in external_list(platform):
        if str(item["name"]) == name:
            return kinds.EXTERNAL[str(item["kind"])].role
    return ""


def problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the external peripherals of the platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        V-P11 for a window under the registers of the entity, V-P12 for
        a missing or unknown `device` or `chip`, V-P13 for two
        peripherals on one instance of a board role, and V-P10 for a
        source pinned to a fixed line of the SoC.
    """
    found: list[Mismatch] = []
    section = platform_dict(platform, "interrupts")
    raw: list[dict[str, Any]] = section.get("sources") or []
    pinned = {str(s["name"]).upper(): int(s["id"]) for s in raw}
    for item in external_list(platform):
        kind = kinds.EXTERNAL[str(item["kind"])]
        found += _variant_problems(item, kind)
        line = pinned.get(str(item["name"]).upper())
        if kind.irq and line in FIXED_LINES:
            found.append(
                _problem(
                    "V-P10",
                    str(item["name"]),
                    f"the source id {line} is a fixed line of the SoC "
                    "(UART, UART_JTAG, SWITCHES, KEYS or FLASH)",
                )
            )
    return found + _instance_problems(platform)


def vhdl_lines(platform: dict[str, Any]) -> str:
    """Write the VHDL tables of the external peripherals.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        Empty without external peripherals. Else `EXT_COUNT`,
        `EXT_INDICES` (the index of each in `PERIPH_BASES`),
        `EXT_IRQ_IDS` (its source in the PLIC, 0 without a line or a
        PLIC) and `<NAME>_EXT_POS`, the position of each in the tables.
        They read `<NAME>_INDEX` and `IRQ_<NAME>`, so they come after
        the interrupt constants.
    """
    items = external_list(platform)
    if not items:
        return ""
    section = platform_dict(platform, "interrupts")
    wired = "sources" in section or "plic" in section
    names = [str(item["name"]).upper() for item in items]
    lines = (
        "\n\t-- Número de periféricos externos do mapa (`kind` de "
        "`Peripherals`), o tamanho das tabelas abaixo.\n"
        f"\tconstant EXT_COUNT : natural := {len(names)};\n"
    )
    lines += table(
        "EXT_INDICES",
        "Índice de cada periférico externo nas tabelas PERIPH_BASES e "
        "PERIPH_MASKS, na ordem de `peripherals`.",
        [f"{name}_INDEX" for name in names],
        "EXT_COUNT",
    )
    lines += table(
        "EXT_IRQ_IDS",
        "Fonte do PLIC de cada periférico externo, na mesma ordem "
        "(zero sem linha ou sem PLIC).",
        [
            f"IRQ_{name}" if wired and _has_irq(item) else "0"
            for name, item in zip(names, items, strict=True)
        ],
        "EXT_COUNT",
    )
    for position, name in enumerate(names):
        lines += (
            f"\t-- Posição de {name} nas tabelas EXT_*.\n"
            f"\tconstant {name}_EXT_POS : natural := {position};\n"
        )
    return lines
