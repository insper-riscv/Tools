"""Lê os arquivos de dados de uma plataforma e de uma placa.

Os esquemas são os do documento 02 do plano Multi-FPGA. Este módulo lê
só os campos que os geradores consomem e recusa o que falta com uma
mensagem que nomeia o arquivo; a validação completa de tipos é a do
módulo de esquemas e substitui esta leitura sem mudar quem a chama.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

# Chaves de `board.memories` que citam um chip do catálogo de tempos.
CHIP_KEYS = ("sdram", "sram", "nor")


class InputError(ValueError):
    """Um arquivo de dados falta ou está malformado."""


@dataclass(frozen=True)
class PinSignal:
    """Um sinal do `pins.yaml` de uma placa.

    Attributes
    ----------
    name : str
        Nome do sinal, com índice entre colchetes quando é barramento.
    pin : str
        Pino do dispositivo, sem prefixo.
    io_standard : str
        Padrão de E/S do Quartus.
    direction : str
        `in`, `out` ou `inout`.
    confirmed : str
        Selo de certeza: `manual`, `repo` ou `inferred`.
    """

    name: str
    pin: str
    io_standard: str
    direction: str
    confirmed: str


@dataclass(frozen=True)
class BoardInputs:
    """Tudo o que os geradores leem para uma plataforma numa placa.

    Attributes
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.
    board : dict of {str: Any}
        O `board.yaml`.
    signals : dict of {str: PinSignal}
        Os sinais do `pins.yaml`, por nome, na ordem do arquivo.
    family : dict of {str: Any}
        O arquivo da família da placa.
    chips : dict of {str: dict of {str: Any}}
        Os chips que a placa cita, por nome, com `extends` resolvido.
    """

    platform: dict[str, Any]
    board: dict[str, Any]
    signals: dict[str, PinSignal]
    family: dict[str, Any]
    chips: dict[str, dict[str, Any]]


def _read_mapping(path: Path) -> dict[str, Any]:
    """Lê um arquivo YAML que deve ser um mapa.

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
        Se o arquivo não existe ou não é um mapa.
    """
    if not path.is_file():
        raise InputError(f"{path}: file not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise InputError(f"{path}: not a YAML mapping")
    return cast(dict[str, Any], data)


def _merge(base: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Mescla dois mapas, com o filho valendo sobre o pai.

    Parameters
    ----------
    base : dict of {str: Any}
        O mapa herdado.
    child : dict of {str: Any}
        O mapa que herda.

    Returns
    -------
    dict of {str: Any}
        O resultado, sem alterar os argumentos.
    """
    out = dict(base)
    for key, value in child.items():
        inherited = out.get(key)
        if isinstance(value, dict) and isinstance(inherited, dict):
            out[key] = _merge(
                cast(dict[str, Any], inherited), cast(dict[str, Any], value)
            )
        else:
            out[key] = value
    return out


def load_chip(chips_dir: Path, name: str) -> dict[str, Any]:
    """Lê um chip do catálogo e resolve a cadeia `extends`.

    Parameters
    ----------
    chips_dir : Path
        A pasta do catálogo de chips.
    name : str
        O nome do chip, que é o nome do arquivo sem `.yaml`.

    Returns
    -------
    dict of {str: Any}
        Os campos do chip, com os herdados já mesclados.

    Raises
    ------
    InputError
        Se um arquivo falta ou a cadeia `extends` forma um ciclo.
    """
    seen: list[str] = []
    chain: list[dict[str, Any]] = []
    current: str | None = name
    while current is not None:
        if current in seen:
            raise InputError(f"chip {current!r}: extends cycle {seen}")
        seen.append(current)
        data = _read_mapping(chips_dir / f"{current}.yaml")
        chain.append(data)
        parent = data.get("extends")
        current = str(parent) if parent else None
    merged: dict[str, Any] = {}
    for data in reversed(chain):
        merged = _merge(merged, data)
    merged.pop("extends", None)
    merged["chip"] = name
    return merged


def _signals(pins_file: Path) -> dict[str, PinSignal]:
    """Lê os sinais de um `pins.yaml`.

    Parameters
    ----------
    pins_file : Path
        O arquivo.

    Returns
    -------
    dict of {str: PinSignal}
        Os sinais por nome, na ordem do arquivo.

    Raises
    ------
    InputError
        Se um sinal não tem os campos obrigatórios ou se repete.
    """
    data = _read_mapping(pins_file)
    out: dict[str, PinSignal] = {}
    for entry in cast(list[dict[str, Any]], data.get("signals") or []):
        try:
            signal = PinSignal(
                name=str(entry["name"]),
                pin=str(entry["pin"]),
                io_standard=str(entry["io_standard"]),
                direction=str(entry["direction"]),
                confirmed=str(entry.get("confirmed", "inferred")),
            )
        except KeyError as error:
            raise InputError(
                f"{pins_file}: signal without {error} in {entry}"
            ) from error
        if signal.name in out:
            raise InputError(f"{pins_file}: signal {signal.name} repeated")
        out[signal.name] = signal
    return out


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
        Se a placa, a família ou um chip não existe.
    """
    platform = _read_mapping(platform_file)
    name = resolve_board_name(platform, board)
    board_dir = boards_dir / name
    if not board_dir.is_dir():
        known = sorted(
            p.name
            for p in boards_dir.iterdir()
            if (p / "board.yaml").is_file()
        )
        raise InputError(
            f"board {name!r} not found in {boards_dir} (known: {known})"
        )
    data = _read_mapping(board_dir / "board.yaml")
    family = _read_mapping(
        boards_dir / "families" / f"{data.get('family')}.yaml"
    )
    memories = cast(dict[str, Any], data.get("memories") or {})
    chips = {
        str(memories[key]["chip"]): load_chip(
            chips_dir, str(memories[key]["chip"])
        )
        for key in CHIP_KEYS
        if key in memories and memories[key].get("chip")
    }
    pins_file = board_dir / str(data.get("pins", "pins.yaml"))
    return BoardInputs(
        platform=platform,
        board=data,
        signals=_signals(pins_file),
        family=family,
        chips=chips,
    )


def board_idcode(boards_dir: Path, name: str) -> str:
    """Lê o IDCODE do FPGA de uma placa, para escolher o cabo.

    Parameters
    ----------
    boards_dir : Path
        A pasta `boards/`.
    name : str
        A placa.

    Returns
    -------
    str
        O IDCODE da entrada `fpga: true` da cadeia JTAG.

    Raises
    ------
    InputError
        Se a placa ou o IDCODE não existe.
    """
    data = _read_mapping(boards_dir / name / "board.yaml")
    jtag = cast(dict[str, Any], data.get("jtag") or {})
    chain = cast(list[dict[str, Any]], jtag.get("chain") or [])
    for entry in chain:
        if entry.get("fpga"):
            return str(entry["idcode"]).upper()
    raise InputError(f"board {name!r}: jtag.chain has no fpga entry")
