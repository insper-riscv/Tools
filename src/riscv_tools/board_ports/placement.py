"""Põe cada periférico externo da plataforma numa cópia do papel.

Os geradores de pinos, o topo e as regras do `board_check` leem a
mesma resposta: para cada periférico externo, que cópia do papel da
placa ele usa e quais sinais ela dá, ou por que a placa não o atende.
"""

from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.memory_map import external
from riscv_tools.memory_map.kinds import EXTERNAL, ExternalKind, Variant


@dataclass(frozen=True)
class Placement:
    """Um periférico externo e a cópia do papel que ele usa.

    Attributes
    ----------
    name : str
        O nome do periférico em `peripherals`.
    kind : ExternalKind
        O `kind` dele no registro.
    variant : Variant or None
        A entidade; `None` quando o campo que a escolhe é inválido (a
        validação do mapa já o recusa).
    instance : int
        A cópia do papel que ele usa.
    pins : dict of {str: str} or None
        O sinal do `pins.yaml` de cada pino do papel; `None` quando a
        placa não atende o periférico.
    need : str
        `required` ou `optional`.
    reason : str
        Por que a placa não atende; vazio quando `pins` existe.
    item : dict of {str: Any}
        A entrada completa de `peripherals`.
    """

    name: str
    kind: ExternalKind
    variant: Variant | None
    instance: int
    pins: dict[str, str] | None
    need: str
    reason: str
    item: dict[str, Any]


def _copy(
    kind: ExternalKind,
    item: dict[str, Any],
    number: int,
    board: dict[str, Any],
) -> tuple[dict[str, str] | None, str]:
    """Acha a cópia do papel da placa que atende o periférico.

    Parameters
    ----------
    kind : ExternalKind
        O `kind` do periférico.
    item : dict of {str: Any}
        A entrada de `peripherals`.
    number : int
        A cópia pedida.
    board : dict of {str: Any}
        O `board.yaml` na forma de mapa (`board_view`).

    Returns
    -------
    tuple of (dict or None, str)
        Os sinais por pino e a razão da recusa, vazia quando atende.
    """
    if kind.role == "video":
        video = cast("dict[str, Any] | None", board.get("video"))
        if video is None:
            return None, "the board has no io.video"
        return {"video": str(video["signals"])}, ""
    buses = cast("dict[str, list[dict[str, Any]]]", board.get("buses") or {})
    copies = buses.get(kind.role, [])
    if not copies:
        return None, f"the board has no bus role {kind.role}"
    if number >= len(copies):
        return None, (
            f"the board has {len(copies)} cop"
            f"{'y' if len(copies) == 1 else 'ies'} of the bus role "
            f"{kind.role} and instance {number} is needed"
        )
    chip = str(item.get("chip", ""))
    found = copies[number]
    if kind.variant_field == "chip" and found["chip"] != chip:
        return None, (
            f"instance {number} of the bus role {kind.role} wires the "
            f"chip {found['chip']}, not {chip}"
        )
    return dict(found["pins"]), ""


def placements(
    platform: dict[str, Any], board: dict[str, Any]
) -> list[Placement]:
    """Põe os periféricos externos da plataforma na placa.

    Parameters
    ----------
    platform : dict of {str: Any}
        A plataforma carregada.
    board : dict of {str: Any}
        O `board.yaml` na forma de mapa (`board_view`).

    Returns
    -------
    list of Placement
        Um por periférico externo, na ordem de `peripherals`.
    """
    numbers = external.instances(platform)
    found: list[Placement] = []
    for item in external.external_list(platform):
        kind = EXTERNAL[str(item["kind"])]
        name = str(item["name"])
        pins, reason = _copy(kind, item, numbers[name], board)
        found.append(
            Placement(
                name,
                kind,
                kind.variant(item),
                numbers[name],
                pins,
                str(item.get("need", "required")),
                reason,
                item,
            )
        )
    return found
