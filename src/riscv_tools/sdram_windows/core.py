"""Tabela de janelas do chip de SDRAM, vista do hospedeiro.

Cada região na SDRAM (`FLASH` e `RAM`) ocupa uma janela do chip: o
endereço de byte do SoC `A` em `[base, base + size)` está no byte
`offset + (A - base)` do chip, isto é, na palavra
`(offset + (A - base)) / 4` do endereço de palavra da porta de
depuração. A tabela vem do `platform.yaml` (`windows_from_platform`) ou
da seção `memory.sdram_windows` da configuração do projeto
(`windows_from_config`), que repete os mesmos números.

```yaml
memory:
  sdram_windows:
    FLASH: {base: 0x1000, size: 0x1FFF000, offset: 0x1000}
    RAM:   {base: 0x40000000, size: 0x2000000, offset: 0x2000000}
```

Sem `offset` a região mantém o endereço do SoC: o byte do chip é o
`base` módulo a menor potência de dois que percorre a região, o mesmo
que o topo gerado faz sem `offset`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from riscv_tools.board_schema.platform_fields import read_platform_file
from riscv_tools.memory_map import chip_split
from riscv_tools.memory_map.core import platform_dict, platform_list
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.layout import FLASH, RAM

WORD_BYTES = 4
_REGIONS = (("rom", FLASH), ("ram", RAM))


class WindowError(ValueError):
    """O endereço ou a região pedida não está na tabela de janelas."""


@dataclass(frozen=True)
class Window:
    """Onde uma região do SoC fica no chip.

    Parameters
    ----------
    name : str
        A região (`FLASH` ou `RAM`).
    base : int
        O primeiro endereço de byte da região no SoC.
    size : int
        Os bytes da região.
    offset : int
        O byte do chip onde a região começa.
    """

    name: str
    base: int
    size: int
    offset: int

    @property
    def end(self) -> int:
        """Dá o primeiro endereço de byte depois da região.

        Returns
        -------
        int
            `base + size`.
        """
        return self.base + self.size

    def contains(self, address: int, length: int = 1) -> bool:
        """Diz se um trecho de bytes cabe na região.

        Parameters
        ----------
        address : int
            O endereço de byte do SoC do primeiro byte.
        length : int, optional
            Quantos bytes, por padrão 1.

        Returns
        -------
        bool
            True quando todos os bytes estão na região.
        """
        return self.base <= address and address + length <= self.end

    def word_address(self, address: int) -> int:
        """Converta um endereço de byte do SoC em palavra do chip.

        Parameters
        ----------
        address : int
            O endereço de byte do SoC, alinhado a palavra.

        Returns
        -------
        int
            O endereço de palavra que a porta de depuração usa.

        Raises
        ------
        WindowError
            Se o endereço não é de palavra ou está fora da região.
        """
        if address % WORD_BYTES:
            raise WindowError(
                f"{self.name}: 0x{address:08x} is not word aligned"
            )
        if not self.contains(address):
            raise WindowError(
                f"{self.name}: 0x{address:08x} is outside "
                f"[0x{self.base:08x}, 0x{self.end:08x})"
            )
        return (self.offset + address - self.base) // WORD_BYTES


def _default_offset(base: int, size: int) -> int:
    """Dá o byte do chip de uma região sem `offset`.

    Parameters
    ----------
    base : int
        O primeiro endereço de byte da região.
    size : int
        Os bytes da região.

    Returns
    -------
    int
        O `base` módulo a menor potência de dois que percorre a região.
    """
    return base % (1 << chip_split.low_bits(base, size))


def windows_from_platform(platform: dict[str, Any]) -> dict[str, Window]:
    """Monta a tabela das regiões que estão na SDRAM.

    Parameters
    ----------
    platform : dict of {str: Any}
        A plataforma lida (com `regions` e `memory`).

    Returns
    -------
    dict of {str: Window}
        A janela de cada região cujo dispositivo é `sdram`.
    """
    memory = platform_dict(platform, "memory")
    regions = {str(r["name"]): r for r in platform_list(platform, "regions")}
    declared = chip_split.windows(platform)
    found: dict[str, Window] = {}
    for key, name in _REGIONS:
        entry = memory.get(key)
        region = regions.get(name)
        device = (
            cast("dict[str, Any]", entry).get("device")
            if isinstance(entry, dict)
            else None
        )
        if region is None or device != "sdram":
            continue
        base, size = evaluate(region["base"]), evaluate(region["size"])
        window = declared.get(name)
        offset = window.offset if window else _default_offset(base, size)
        found[name] = Window(name, base, size, offset)
    return found


def windows_from_platform_file(path: Path) -> dict[str, Window]:
    """Lê um `platform.yaml` e monta a tabela de janelas.

    Parameters
    ----------
    path : Path
        O arquivo.

    Returns
    -------
    dict of {str: Window}
        A tabela (ver `windows_from_platform`).
    """
    return windows_from_platform(read_platform_file(path))


def windows_from_config(cfg: dict[str, Any]) -> dict[str, Window]:
    """Monta a tabela a partir da configuração do projeto.

    Parameters
    ----------
    cfg : dict of {str: Any}
        A configuração mesclada: `memory.sdram_windows` ou, sem ela, a
        RAM de `memory.ram_base` e `memory.ram_words` no byte 0 do chip.

    Returns
    -------
    dict of {str: Window}
        A tabela; vazia quando a configuração não tem SDRAM.
    """
    memory = cast("dict[str, Any]", cfg.get("memory") or {})
    table = cast("dict[str, Any] | None", memory.get("sdram_windows"))
    if table:
        return {
            str(name): Window(
                str(name),
                evaluate(entry["base"]),
                evaluate(entry["size"]),
                evaluate(entry.get("offset", 0)),
            )
            for name, entry in table.items()
        }
    if memory.get("ram_base") is None:
        return {}
    words = memory.get("ram_words")
    size = 0 if words is None else int(words) * WORD_BYTES
    return {RAM: Window(RAM, int(memory["ram_base"]), size, 0)}


def window_named(windows: dict[str, Window], name: str) -> Window:
    """Acha a janela de uma região pelo nome.

    Parameters
    ----------
    windows : dict of {str: Window}
        A tabela.
    name : str
        `FLASH` ou `RAM`, sem diferenciar maiúsculas.

    Returns
    -------
    Window
        A janela.

    Raises
    ------
    WindowError
        Se a região não está na SDRAM.
    """
    window = windows.get(name.upper())
    if window is None:
        known = ", ".join(sorted(windows)) or "none"
        raise WindowError(
            f"region {name} is not in the sdram (regions there: {known})"
        )
    return window
