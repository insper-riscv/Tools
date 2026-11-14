"""The `rv32_platform.h` of the test programs, from the platform.

The header gives the memory map as plain `#define` numbers, so assembly
(`.S`) and C programs use it alike, and the macros that end an assembly
test. It is asked under `generate`:

```yaml
generate:
  platform_h:
    path: tools/riscv_build/include-demo/rv32_platform.h
```

The numbers come from the platform, so no copy is typed by hand: the
RAM and the host words (`RV32_RAM_BASE`, `RV32_RAM_END`,
`RV32_STDOUT_BASE`, `RV32_TOHOST`), the base of each peripheral
(`RV32_<NAME>_BASE`) and of each group of a block of the GPIO or of the
display (`RV32_<NAME>_G<k>_BASE`), the banks of the FLASH and the ticks
of the `mtime`.
"""

import re
from typing import Any

from riscv_tools.flash_image import MAGIC
from riscv_tools.memory_map import interrupts
from riscv_tools.memory_map.core import peripheral_list
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.groups import GROUP_BYTES
from riscv_tools.memory_map.kinds import is_group_block

_HEAD = """\
/* O mapa de memória da plataforma {platform}, como números simples que um
 * programa em assembly usa tanto quanto um em C. Gerado por
 * `riscv-tools generate-memory-map` a partir de {source}; não edite à mão.
 *
 * Os números ficam em #define (e não em constexpr ou enum) porque o assembly
 * (.S) inclui este arquivo e só o pré-processador os enxerga. */
#ifndef RV32_PLATFORM_H
#define RV32_PLATFORM_H

"""
_TAIL = """\

#ifdef __ASSEMBLER__
/* Como um teste em assembly termina, com os nomes do modelo do
 * riscv-arch-test. tohost = 1 é aprovação, (código << 1) | 1 é falha com
 * esse código. Altera t0 e t1. */
#define RVMODEL_HALT_PASS \\
    li   t0, RV32_TOHOST; \\
    li   t1, 1; \\
    sw   t1, 0(t0); \\
    sw   x0, 4(t0); \\
    tail rv32_wait_restart
#define RVMODEL_HALT_FAIL(code) \\
    li   t0, RV32_TOHOST; \\
    li   t1, ((code) << 1) | 1; \\
    sw   t1, 0(t0); \\
    sw   x0, 4(t0); \\
    tail rv32_wait_restart
#endif

#endif
"""
_BANK = re.compile(r"^BANK_([A-Z0-9]+)\.base$")


def _define(name: str, value: int, comment: str = "") -> str:
    """Write one `#define` line.

    Parameters
    ----------
    name : str
        The macro.
    value : int
        The number, written in hexadecimal with 8 digits.
    comment : str, optional
        What the number is.

    Returns
    -------
    str
        The line, with the comment after it when there is one.
    """
    text = f"#define {name} 0x{value:08X}"
    return f"{text}   /* {comment} */" if comment else text


def _peripheral_lines(platform: dict[str, Any]) -> list[str]:
    """Write the bases of the peripherals and of their groups.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.

    Returns
    -------
    list of str
        `RV32_<NAME>_BASE` of each peripheral, then the
        `RV32_<NAME>_G<k>_BASE` of each group of a block of the GPIO or
        of the display.
    """
    lines: list[str] = []
    for periph in peripheral_list(platform):
        name = str(periph["name"]).upper()
        base = int(evaluate(periph["base"]))
        lines.append(_define(f"RV32_{name}_BASE", base))
        if is_group_block(periph):
            groups = int(periph["size"]) // GROUP_BYTES
            lines.extend(
                _define(f"RV32_{name}_G{k}_BASE", base + GROUP_BYTES * k)
                for k in range(groups)
            )
    return lines


def _bank_lines(table: dict[str, int]) -> list[str]:
    """Write the banks of the FLASH.

    Parameters
    ----------
    table : dict of {str: int}
        The symbols of the map.

    Returns
    -------
    list of str
        The magic number and, for each bank, its base and size; empty
        without banks.
    """
    banks = sorted(m[1] for key in table if (m := _BANK.match(key)))
    if not banks:
        return []
    lines = ["", _define("RV32_IMAGE_MAGIC", MAGIC)]
    for bank in banks:
        lines.append(
            _define(f"RV32_BANK_{bank}_BASE", table[f"BANK_{bank}.base"])
        )
        lines.append(
            _define(f"RV32_BANK_{bank}_SIZE", table[f"BANK_{bank}.size"])
        )
    return lines


def render_platform_h(
    platform: dict[str, Any], table: dict[str, int], source: str
) -> str:
    """Render the header of the test programs.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    table : dict of {str: int}
        The symbols of the map.
    source : str
        The platform file, for the header.

    Returns
    -------
    str
        The file.
    """
    lines = [
        _define("RV32_RAM_BASE", table["RAM.base"], "primeiro byte da RAM"),
        _define("RV32_RAM_END", table["RAM.end"], "um após o último byte"),
    ]
    for word, macro in (
        ("stdout.base", "RV32_STDOUT_BASE"),
        ("tohost.base", "RV32_TOHOST"),
    ):
        if word in table:
            lines.append(_define(macro, table[word]))
    lines += ["", *_peripheral_lines(platform), *_bank_lines(table)]
    if interrupts.declared(platform):
        tick = interrupts.tick_cycles(platform)
        lines += ["", f"#define RV32_TICK_CYCLES {tick}"]
    head = _HEAD.format(platform=platform.get("platform", ""), source=source)
    return head + "\n".join(lines) + "\n" + _TAIL
