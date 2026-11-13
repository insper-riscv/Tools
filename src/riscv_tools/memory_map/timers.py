"""The general-purpose timers of a platform: any number of them.

A timer is an entry of `peripherals` with `kind: timer`, with a free
name, its own `base` and its own window (`size` of at least 32 bytes,
the eight registers of the timer):

```yaml
peripherals:
  TIMER0:
    kind: timer
    base: 0x80006000
    size: 64
  TIMER1:
    kind: timer
    base: 0x80006100
    size: 64
```

The entry named `TIMER`, with no `kind`, is a timer too, so the
platforms that have one timer keep working as they are written.

Each timer has one interrupt source of the PLIC. A source that
`interrupts.sources` names keeps its number; a timer that it does not
name takes the smallest number from 5 up that no source uses and that
is not one of the fixed lines of the SoC, in the order of
`peripherals`. The number of a timer therefore depends only on the
file, and the sources of the other peripherals never move.
"""

import re
from typing import Any

from riscv_tools.memory_map.core import (
    Mismatch,
    peripheral_list,
    platform_dict,
)

KIND_TIMER = "timer"
KINDS = (KIND_TIMER,)
# A entrada sem `kind` com este nome é um temporizador.
DEFAULT_TIMER_NAME = "TIMER"
# As linhas do PLIC que o SoC liga por nome, fora a do temporizador:
# UART, UART_JTAG, SWITCHES, KEYS e FLASH.
FIXED_LINES = (1, 2, 3, 4, 6)
FIRST_TIMER_LINE = 5
# Menor janela de um temporizador: oito registradores de uma palavra.
TIMER_MIN_SIZE = 32
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*")


def kind_of(item: dict[str, Any]) -> str | None:
    """Tell the kind of a peripheral.

    Parameters
    ----------
    item : dict of {str: Any}
        One entry of `peripherals`, with its `name`.

    Returns
    -------
    str or None
        The `kind` as written; `timer` for the entry named `TIMER`
        that has none; None for any other peripheral.
    """
    if "kind" in item:
        return str(item["kind"])
    if str(item["name"]).upper() == DEFAULT_TIMER_NAME:
        return KIND_TIMER
    return None


def timer_list(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """List the timers of the platform, in the order of `peripherals`.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of dict of {str: Any}
        The completed entries (see `peripheral_list`) of kind `timer`.
    """
    return [
        item
        for item in peripheral_list(platform)
        if kind_of(item) == KIND_TIMER
    ]


def has_timer(platform: dict[str, Any]) -> bool:
    """Tell whether the platform has at least one timer.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    bool
        True when one entry of `peripherals` is a timer.
    """
    return bool(timer_list(platform))


def auto_lines(taken: set[int], count: int) -> list[int]:
    """Choose the interrupt lines of the timers that no source names.

    Parameters
    ----------
    taken : set of int
        The numbers that the sources already use.
    count : int
        How many lines are needed.

    Returns
    -------
    list of int
        The smallest numbers from `FIRST_TIMER_LINE` up that are
        neither in `taken` nor one of `FIXED_LINES`, in ascending
        order.
    """
    found: list[int] = []
    line = FIRST_TIMER_LINE
    while len(found) < count:
        if line not in taken and line not in FIXED_LINES:
            found.append(line)
        line += 1
    return found


def problems(platform: dict[str, Any]) -> list[Mismatch]:
    """Check the names, the kinds and the windows of the peripherals.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of Mismatch
        V-P6 for a kind that does not exist, V-P7 for a timer window
        under 32 bytes, V-P8 for a name that is not a VHDL identifier
        or that repeats once in upper case, and V-P9 for a timer
        pinned to a line that the SoC wires to another peripheral.
    """
    found: list[Mismatch] = []
    seen: set[str] = set()
    pinned = _pinned(platform)
    for item in peripheral_list(platform):
        name = str(item["name"])
        found += _name_problems(name, seen)
        seen.add(name.upper())
        kind = kind_of(item)
        if "kind" in item and kind not in KINDS:
            found.append(
                _problem(
                    "V-P6", name, f"kind {kind!r} is not one of {list(KINDS)}"
                )
            )
        if kind == KIND_TIMER:
            found += _timer_problems(item, pinned.get(name.upper()))
    return found


def _problem(code: str, name: str, detail: str) -> Mismatch:
    """Write one problem of a peripheral."""
    return Mismatch("platform", "", f"{code} peripheral {name}: {detail}")


def _name_problems(name: str, seen: set[str]) -> list[Mismatch]:
    """Check one name against the identifiers and the earlier names."""
    found: list[Mismatch] = []
    if not _NAME.fullmatch(name):
        found.append(
            _problem(
                "V-P8",
                name,
                "the name must be letters, digits and single underscores, "
                "starting with a letter (it becomes `<NAME>_BASE` and "
                "`<NAME>_INDEX` in VHDL)",
            )
        )
    if name.upper() in seen:
        found.append(_problem("V-P8", name, "the name repeats in upper case"))
    return found


def _timer_problems(
    item: dict[str, Any], pinned: int | None
) -> list[Mismatch]:
    """Check the window and the pinned line of one timer."""
    found: list[Mismatch] = []
    name = str(item["name"])
    if int(item.get("size", TIMER_MIN_SIZE)) < TIMER_MIN_SIZE:
        found.append(
            _problem(
                "V-P7",
                name,
                f"a timer needs `size` of at least {TIMER_MIN_SIZE} "
                "bytes, the eight registers",
            )
        )
    if pinned in FIXED_LINES:
        found.append(
            _problem(
                "V-P9",
                name,
                f"the source id {pinned} is a fixed line of the SoC "
                "(UART, UART_JTAG, SWITCHES, KEYS or FLASH)",
            )
        )
    return found


def _pinned(platform: dict[str, Any]) -> dict[str, int]:
    """Read the ids of `interrupts.sources`, by upper-case name."""
    section = platform_dict(platform, "interrupts")
    raw: list[dict[str, Any]] = section.get("sources") or []
    return {str(s["name"]).upper(): int(s["id"]) for s in raw}


def _table(name: str, comment: str, rows: list[str]) -> str:
    """Write one table of the timers, an array of `integer_vector`."""
    body = (
        ",\n".join(f"\t\t{i} => {row}" for i, row in enumerate(rows))
        if rows
        else "\t\tothers => 0"
    )
    return (
        f"\t-- {comment}\n"
        f"\tconstant {name} : integer_vector(0 to TIMER_COUNT - 1) := "
        f"(\n{body}\n\t);\n"
    )


def vhdl_lines(platform: dict[str, Any]) -> str:
    """Write the VHDL tables of the timers.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    str
        `TIMER_COUNT`, then `TIMER_INDICES` (the index of each timer in
        `PERIPH_BASES`) and `TIMER_IRQ_IDS` (its source in the PLIC, 0
        without a PLIC), each preceded by a blank line; the tables are
        empty without timers. They read `<NAME>_INDEX` and `IRQ_<NAME>`
        of the lines above, so they come after the interrupt constants.
    """
    names = [str(item["name"]).upper() for item in timer_list(platform)]
    section = platform_dict(platform, "interrupts")
    wired = "sources" in section or "plic" in section
    lines = (
        "\n\t-- Número de temporizadores de uso geral do mapa (`kind: "
        "timer`), o tamanho das tabelas abaixo.\n"
        f"\tconstant TIMER_COUNT : natural := {len(names)};\n"
    )
    lines += _table(
        "TIMER_INDICES",
        "Índice de cada temporizador nas tabelas PERIPH_BASES e "
        "PERIPH_MASKS, na ordem de `peripherals`.",
        [f"{name}_INDEX" for name in names],
    )
    return lines + _table(
        "TIMER_IRQ_IDS",
        "Fonte do PLIC de cada temporizador, na mesma ordem (zero sem PLIC).",
        [f"IRQ_{name}" if wired else "0" for name in names],
    )
