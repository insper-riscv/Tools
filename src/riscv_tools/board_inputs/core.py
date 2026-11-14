"""Reúne os dados dos geradores pelo catálogo do `board_schema`.

A leitura e a validação dos arquivos são as do `board_schema` (um só
leitor de `board.yaml`, `pins.yaml`, família e chip). Este módulo só
escolhe a placa, carrega o que a plataforma usa e entrega os registros
tipados na forma de mapas que os geradores consomem.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.board_schema import (
    Board,
    Catalog,
    Chip,
    Family,
    NotFoundError,
    Pin,
    SchemaError,
    VideoMode,
    VideoRole,
)
from riscv_tools.memory_map.platform_format import normalize

# Chaves de `board.memories` que citam um chip do catálogo de tempos.
CHIP_KEYS = ("sdram", "sram", "nor")
# Um sinal do `pins.yaml` é o registro `Pin` do `board_schema`.
PinSignal = Pin


class InputError(ValueError):
    """Um arquivo de dados falta ou não segue o esquema."""


@dataclass(frozen=True)
class BoardInputs:
    """Tudo o que os geradores leem para uma plataforma numa placa.

    Attributes
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.
    board : dict of {str: Any}
        O `board.yaml` na forma de mapa (ver `board_view`).
    signals : dict of {str: Pin}
        Os sinais do `pins.yaml`, por nome, na ordem do arquivo.
    family : dict of {str: Any}
        A família da placa na forma de mapa.
    chips : dict of {str: dict of {str: Any}}
        Os chips que a placa cita, por nome.
    video : VideoRole or None
        A saída de vídeo da placa; `None` sem ela.
    video_modes : dict of {str: VideoMode}
        O catálogo de modos de vídeo, lido só quando a placa tem vídeo.
    """

    platform: dict[str, Any]
    board: dict[str, Any]
    signals: dict[str, Pin]
    family: dict[str, Any]
    chips: dict[str, dict[str, Any]]
    video: VideoRole | None = None
    video_modes: dict[str, VideoMode] = field(
        default_factory=dict[str, VideoMode]
    )


def board_view(board: Board) -> dict[str, Any]:
    """Escreve o registro da placa como mapa.

    Parameters
    ----------
    board : Board
        A placa lida pelo `board_schema`.

    Returns
    -------
    dict of {str: Any}
        Os campos que os geradores leem, com os nomes do `board.yaml`.
    """
    clocks = board.clocks
    uart = board.console.uart
    return {
        "board": board.board,
        "family": board.family,
        "device": board.device,
        "clocks": {
            "inputs": [
                {"name": c.name, "signal": c.signal, "mhz": c.mhz}
                for c in clocks.inputs
            ],
            "reference": clocks.reference,
            "reset": {
                "signal": clocks.reset_signal,
                "active": clocks.reset_active,
            },
        },
        "io": {
            role: {
                "signals": spec.signals,
                "active": spec.active,
                "groups": list(spec.all_groups),
                "bidirectional": spec.bidirectional,
            }
            for role, spec in board.io.items()
        },
        "memories": {
            kind: {
                "chip": mem.chip,
                "chips": mem.chips,
                "bus_width": mem.bus_width,
                "signals": list(mem.signals),
                "clk_phase_ps": mem.clk_phase_ps,
            }
            for kind, mem in board.memories.items()
        },
        "console": {"uart": {"rx": uart[0], "tx": uart[1]} if uart else {}},
    }


def family_view(family: Family) -> dict[str, Any]:
    """Escreve o registro da família como mapa.

    Parameters
    ----------
    family : Family
        A família lida pelo `board_schema`.

    Returns
    -------
    dict of {str: Any}
        `quartus_family`, `slew_rate` e a seção `pll`.
    """
    pll = family.pll
    return {
        "family": family.family,
        "quartus_family": family.quartus_family,
        "slew_rate": family.slew_rate,
        "qsf": list(family.qsf),
        "pll": {
            "ip": pll.ip,
            "vco_mhz": list(pll.vco_mhz),
            "clock_node_pattern": pll.clock_node_pattern,
            "outputs_max": pll.outputs_max,
        },
    }


def chip_view(chip: Chip) -> dict[str, Any]:
    """Escreve o registro do chip como mapa, sem os campos ausentes.

    Parameters
    ----------
    chip : Chip
        O chip lido pelo `board_schema`, com `extends` resolvido.

    Returns
    -------
    dict of {str: Any}
        Os campos do catálogo que existem para o chip.
    """
    fields: dict[str, Any] = {
        "chip": chip.chip,
        "kind": chip.kind,
        "organization": dict(chip.organization),
        "timing": dict(chip.timing),
        "io_timing": dict(chip.io_timing),
        "max_mhz": chip.max_mhz,
        "cas_latency": chip.cas_latency,
        "sector_bytes": chip.sector_bytes,
        "boot_sector_bytes": chip.boot_sector_bytes,
    }
    return {k: v for k, v in fields.items() if v is not None}


def resolve_board_name(platform: dict[str, Any], board: str | None) -> str:
    """Escolhe a placa de uma geração.

    Parameters
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.
    board : str or None
        A placa pedida na linha de comando.

    Returns
    -------
    str
        O nome pedido; ou o do campo `board`; ou a única placa de
        `boards`.

    Raises
    ------
    InputError
        Se nada define a placa ou `boards` tem mais de uma.
    """
    if board:
        return board
    named = str(platform.get("board", "auto"))
    if named != "auto":
        return named
    boards = cast(list[str], platform.get("boards") or [])
    if len(boards) == 1:
        return boards[0]
    raise InputError(
        f"platform {platform.get('platform')!r}: pass --board "
        f"(boards: {boards})"
    )


def _read_platform(path: Path) -> dict[str, Any]:
    """Lê o `platform.yaml`.

    Parameters
    ----------
    path : Path
        O arquivo.

    Returns
    -------
    dict of {str: Any}
        O conteúdo.

    Raises
    ------
    InputError
        Se o arquivo falta ou não é um mapa.
    """
    if not path.is_file():
        raise InputError(f"{path}: file not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InputError(f"{path}: not a YAML mapping")
    platform = cast(dict[str, Any], data)
    try:
        normalize(platform, path)
    except ValueError as error:
        raise InputError(f"{path}: {error}") from error
    return platform


def load_inputs(
    platform_file: Path,
    board: str | None,
    boards_dir: Path,
    chips_dir: Path,
) -> BoardInputs:
    """Lê os arquivos de uma plataforma numa placa.

    Parameters
    ----------
    platform_file : Path
        O `platform.yaml`.
    board : str or None
        A placa; `None` usa a da plataforma (ver `resolve_board_name`).
    boards_dir : Path
        A pasta `boards/`, com uma pasta por placa e `families/`.
    chips_dir : Path
        O catálogo de chips.

    Returns
    -------
    BoardInputs
        Os dados lidos.

    Raises
    ------
    InputError
        Se a placa, a família ou um chip não existe ou não segue o
        esquema.
    """
    platform = _read_platform(platform_file)
    name = resolve_board_name(platform, board)
    catalog = Catalog(boards_dir, chips_dir)
    try:
        spec = catalog.load_board(name)
        pins = catalog.load_pins(name, spec)
        family = catalog.load_family(spec.family)
        chips = {
            str(mem.chip): chip_view(catalog.load_chip(mem.chip))
            for kind, mem in spec.memories.items()
            if kind in CHIP_KEYS and mem.chip
        }
        modes = catalog.load_video_modes() if spec.video else {}
    except NotFoundError as error:
        raise InputError(
            f"{error.kind} {error.name!r} not found in {boards_dir} "
            f"(known: {error.known})"
        ) from error
    except SchemaError as error:
        raise InputError(str(error)) from error
    return BoardInputs(
        platform,
        board_view(spec),
        {pin.name: pin for pin in pins},
        family_view(family),
        chips,
        spec.video,
        modes,
    )
