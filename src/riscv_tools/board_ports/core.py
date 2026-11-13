"""Transforma papéis de E/S, relógio, reset e memórias em portas.

Os geradores de pinos, de `.sdc` e de topo leem as mesmas portas, de
modo que o nome, a largura e o pino de cada sinal nascem aqui uma só
vez. Os nomes de pino do `pins.yaml` aceitam dois formatos de
barramento, `LEDR[3]` e `LEDR3`; a porta é sempre um vetor `LEDR`.
"""

import re
from dataclasses import dataclass, field
from typing import Any, cast

from riscv_tools.board_inputs import BoardInputs, InputError, PinSignal

_SEGMENTS = 7
# Papéis de E/S, na ordem em que viram portas.
IO_ROLES = ("leds", "switches", "keys", "display", "video")
# O vídeo não vira porta aqui, porque os pinos dele entram junto com o
# periférico.
PORT_ROLES = tuple(role for role in IO_ROLES if role != "video")
_MEMORY_KEYS = ("sdram", "sram", "nor")
_VECTOR = re.compile(r"^(\w+)\[(\d+):(\d+)\]$")
_DISPLAY = re.compile(r"^(\w+)\[(\d+):(\d+)\]\[(\d+):(\d+)\]$")
_BRACKET = re.compile(r"^(.+)\[(\d+)\]$")
_FLAT = re.compile(r"^(.*[A-Za-z_])(\d+)$")


@dataclass(frozen=True)
class Port:
    """Uma porta do topo da placa.

    Attributes
    ----------
    name : str
        Nome da porta, igual ao do sinal (escalar) ou ao radical
        (vetor).
    role : str
        `clock`, `reset`, `leds`, `switches`, `keys`, `display`,
        `uart`, `sdram`, `sram` ou `nor`.
    direction : str
        `in`, `out` ou `inout`.
    signals : tuple of PinSignal
        Um sinal por bit, do bit 0 em diante.
    vector : bool
        Verdadeiro quando a porta é `std_logic_vector`.
    active : str
        Polaridade do papel de E/S, `high` ou `low`.
    alias : str
        Expressão VHDL de um bit de outra porta que esta porta usa no
        lugar de um pino próprio (o reset em `KEY[0]`); vazio quando a
        porta tem pino.
    """

    name: str
    role: str
    direction: str
    signals: tuple[PinSignal, ...]
    vector: bool
    active: str = "high"
    alias: str = ""

    @property
    def width(self) -> int:
        """Largura da porta em bits."""
        return len(self.signals)

    @property
    def bit_names(self) -> tuple[str, ...]:
        """Nomes dos bits como o Quartus os enxerga (`LEDR[3]`)."""
        if not self.vector:
            return (self.name,)
        return tuple(f"{self.name}[{i}]" for i in range(self.width))


@dataclass(frozen=True)
class PortPlan:
    """As portas de um topo e os avisos achados ao montá-las.

    Attributes
    ----------
    ports : tuple of Port
        As portas, na ordem do topo.
    warnings : list of str
        Avisos (papel opcional ausente).
    """

    ports: tuple[Port, ...]
    warnings: list[str] = field(default_factory=list[str])


def _signal(inputs: BoardInputs, name: str) -> PinSignal:
    """Busca um sinal no `pins.yaml` ou falha com o nome ausente.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    name : str
        Nome do sinal.

    Returns
    -------
    PinSignal
        O sinal.

    Raises
    ------
    InputError
        Se o `pins.yaml` não tem o sinal.
    """
    found = inputs.signals.get(name)
    if found is None:
        raise InputError(
            f"board {inputs.board.get('board')!r}: pins.yaml has no "
            f"signal {name!r}"
        )
    return found


def _first(inputs: BoardInputs, names: list[str]) -> PinSignal:
    """Busca o primeiro dos nomes que existe no `pins.yaml`.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    names : list of str
        Grafias possíveis do mesmo sinal.

    Returns
    -------
    PinSignal
        O primeiro sinal achado.

    Raises
    ------
    InputError
        Se nenhuma grafia existe.
    """
    for name in names:
        if name in inputs.signals:
            return inputs.signals[name]
    raise InputError(
        f"board {inputs.board.get('board')!r}: pins.yaml has none of {names}"
    )


def _vector_port(
    inputs: BoardInputs, role: str, spec: str, active: str
) -> list[Port]:
    """Monta o vetor de um papel `NOME[hi:lo]` ou o escalar `NOME`.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    role : str
        O papel.
    spec : str
        O grupo do `board.yaml` (`LEDR[9:0]`).
    active : str
        Polaridade do papel.

    Returns
    -------
    list of Port
        Uma porta.
    """
    found = _VECTOR.match(spec)
    if found is None:
        sig = _signal(inputs, spec)
        return [Port(spec, role, sig.direction, (sig,), False, active)]
    name, high, low = found.group(1), int(found[2]), int(found[3])
    bits = tuple(
        _first(inputs, [f"{name}[{i}]", f"{name}{i}"])
        for i in range(min(high, low), max(high, low) + 1)
    )
    return [Port(name, role, bits[0].direction, bits, True, active)]


def _display_ports(inputs: BoardInputs, spec: str, active: str) -> list[Port]:
    """Monta uma porta por dígito de um display `HEX[5:0][6:0]`.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    spec : str
        O grupo do `board.yaml`.
    active : str
        Polaridade do papel.

    Returns
    -------
    list of Port
        Uma porta `HEX<d>` por dígito, em ordem crescente.

    Raises
    ------
    InputError
        Se a grafia do grupo não é a do display.
    """
    found = _DISPLAY.match(spec)
    if found is None:
        raise InputError(
            f"io.display signals {spec!r}: expected NAME[d:d][s:s]"
        )
    name = found.group(1)
    digits = sorted((int(found[2]), int(found[3])))
    segments = sorted((int(found[4]), int(found[5])))
    ports: list[Port] = []
    for digit in range(digits[0], digits[1] + 1):
        bits = tuple(
            _first(
                inputs,
                [f"{name}{digit}[{seg}]", f"{name}{digit}{seg}"],
            )
            for seg in range(segments[0], segments[1] + 1)
        )
        ports.append(
            Port(f"{name}{digit}", "display", "out", bits, True, active)
        )
    return ports


def _role_ports(
    inputs: BoardInputs, role: str, active: str, spec: str
) -> list[Port]:
    """Monta as portas de um papel de E/S.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    role : str
        O papel.
    active : str
        Polaridade do papel.
    spec : str
        O grupo do `board.yaml`.

    Returns
    -------
    list of Port
        As portas do papel.
    """
    if role == "display":
        return _display_ports(inputs, spec, active)
    return _vector_port(inputs, role, spec, active)


def _offered_ports(inputs: BoardInputs, role: str) -> tuple[list[Port], int]:
    """Monta as portas que a placa oferece para um papel.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    role : str
        O papel.

    Returns
    -------
    tuple of (list of Port, int)
        As portas e quantos itens elas dão (dígitos, no display).
    """
    offered = cast(dict[str, Any], inputs.board.get("io") or {})
    found = cast(dict[str, Any], offered.get(role) or {})
    if not found:
        return [], 0
    made = _role_ports(
        inputs, role, str(found.get("active", "high")), str(found["signals"])
    )
    items = sum(p.width for p in made)
    return made, items // _SEGMENTS if role == "display" else items


def _io_ports(inputs: BoardInputs) -> PortPlan:
    """Monta as portas dos papéis de E/S que a plataforma pede.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    PortPlan
        As portas e os avisos de papel opcional ausente.

    Raises
    ------
    InputError
        Se um papel obrigatório falta ou tem menos bits que o pedido.
    """
    wanted = cast(dict[str, Any], inputs.platform.get("io") or {})
    name = inputs.board.get("board")
    ports: list[Port] = []
    warnings: list[str] = []
    for role in PORT_ROLES:
        request = cast(dict[str, Any], wanted.get(role) or {})
        if not request:
            continue
        count = int(request.get("count", 0))
        made, have = _offered_ports(inputs, role)
        if have >= count:
            ports.extend(made)
        elif request.get("need") == "required":
            raise InputError(
                f"E io.{role} count {count} required but board {name!r} "
                f"has {have or 'none'}"
            )
        else:
            warnings.append(
                f"W io.{role} optional and not on board {name!r}; the "
                f"{role} peripheral is omitted"
            )
    return PortPlan(tuple(ports), warnings)


def _split(name: str) -> tuple[str, int | None, bool]:
    """Separa o radical e o índice de um nome de sinal.

    Parameters
    ----------
    name : str
        Nome do sinal (`DRAM_DQ[3]`, `DRAM_DQ3` ou `DRAM_CLK`).

    Returns
    -------
    tuple of (str, int or None, bool)
        Radical, índice e se o índice veio sem colchetes.
    """
    bracket = _BRACKET.match(name)
    if bracket:
        return bracket.group(1), int(bracket.group(2)), False
    flat = _FLAT.match(name)
    if flat:
        return flat.group(1), int(flat.group(2)), True
    return name, None, False


def _direction(members: list[PinSignal], stem: str) -> str:
    """Resolve a direção de uma porta a partir dos seus bits.

    Parameters
    ----------
    members : list of PinSignal
        Os bits da porta.
    stem : str
        O radical, para a mensagem.

    Returns
    -------
    str
        `inout` se algum bit é bidirecional, senão a direção comum.

    Raises
    ------
    InputError
        Se os bits misturam entrada e saída.
    """
    kinds = {m.direction for m in members}
    if "inout" in kinds:
        return "inout"
    if len(kinds) > 1:
        raise InputError(f"signals of {stem} mix directions {sorted(kinds)}")
    return kinds.pop()


def _group_ports(
    inputs: BoardInputs, role: str, prefixes: list[str]
) -> list[Port]:
    """Agrupa os sinais de uma memória em portas.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    role : str
        O tipo da memória.
    prefixes : list of str
        Prefixos do grupo (`DRAM`); um sinal pertence ao grupo se
        começa com o prefixo e `_`.

    Returns
    -------
    list of Port
        Uma porta por radical, na ordem em que aparece no `pins.yaml`.

    Raises
    ------
    InputError
        Se o grupo é vazio ou um barramento tem índice faltando.
    """
    parsed: dict[str, list[tuple[int | None, bool, PinSignal]]] = {}
    for sig in inputs.signals.values():
        if any(sig.name.startswith(f"{p}_") for p in prefixes):
            stem, index, flat = _split(sig.name)
            parsed.setdefault(stem, []).append((index, flat, sig))
    if not parsed:
        raise InputError(f"no signal of memory {role} ({prefixes}_*)")
    return [_stem_port(stem, items, role) for stem, items in parsed.items()]


def _stem_port(
    stem: str, items: list[tuple[int | None, bool, PinSignal]], role: str
) -> Port:
    """Monta a porta de um radical de sinal.

    Parameters
    ----------
    stem : str
        O radical.
    items : list of tuple
        Índice, se veio sem colchetes e o sinal de cada membro.
    role : str
        O papel.

    Returns
    -------
    Port
        Escalar quando há um membro sem colchetes ou nenhum índice;
        senão vetor.

    Raises
    ------
    InputError
        Se os índices não são contíguos a partir de 0.
    """
    indexed = [(i, sig) for i, _, sig in items if i is not None]
    if not indexed or (len(items) == 1 and items[0][1]):
        return _scalar(items[0][2], role)
    ordered = sorted(indexed, key=lambda item: item[0])
    if [i for i, _ in ordered] != list(range(len(ordered))):
        raise InputError(f"signals of {stem} are not contiguous from 0")
    bits = tuple(sig for _, sig in ordered)
    return Port(stem, role, _direction(list(bits), stem), bits, True)


def _scalar(sig: PinSignal, role: str) -> Port:
    """Monta uma porta escalar.

    Parameters
    ----------
    sig : PinSignal
        O sinal.
    role : str
        O papel da porta.

    Returns
    -------
    Port
        A porta, com o nome do sinal.
    """
    return Port(sig.name, role, sig.direction, (sig,), False)


def _used_devices(inputs: BoardInputs) -> list[str]:
    """Lista os dispositivos que os backends da plataforma usam.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    list of str
        Os valores de `device` dos backends `dispositivo`.
    """
    memory = cast(dict[str, Any], inputs.platform.get("memory") or {})
    regions = [
        cast(dict[str, Any], r) for r in memory.values() if isinstance(r, dict)
    ]
    return [
        str(r["device"])
        for r in regions
        if r.get("backend") == "dispositivo"
        and r.get("device") in _MEMORY_KEYS
    ]


def _memory_ports(inputs: BoardInputs) -> list[Port]:
    """Monta as portas das memórias de dispositivo que a plataforma usa.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    list of Port
        As portas das memórias, uma memória após a outra.

    Raises
    ------
    InputError
        Se a plataforma pede um dispositivo que a placa não tem.
    """
    offered = cast(dict[str, Any], inputs.board.get("memories") or {})
    used = _used_devices(inputs)
    ports: list[Port] = []
    for kind in (k for k in _MEMORY_KEYS if k in used):
        if kind not in offered:
            raise InputError(
                f"E memory device {kind} is not provided by board "
                f"{inputs.board.get('board')!r}; use backend emulado"
            )
        ports.extend(
            _group_ports(inputs, kind, _prefixes(offered[kind]["signals"]))
        )
    return ports


def _prefixes(raw: object) -> list[str]:
    """Lê os prefixos de um grupo de sinais de memória.

    Parameters
    ----------
    raw : object
        O campo `signals` da memória: um texto ou uma lista de textos.

    Returns
    -------
    list of str
        Os prefixos.
    """
    if isinstance(raw, list):
        return [str(p) for p in cast(list[Any], raw)]
    return [str(raw)]


def _uart_ports(inputs: BoardInputs) -> list[Port]:
    """Monta as portas da UART de pinos quando o console as pede.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    list of Port
        As portas `rx` e `tx`; vazio com o console `jtag`.

    Raises
    ------
    InputError
        Se o console é `pinos` e a placa não declara a UART.
    """
    if inputs.platform.get("console") != "pinos":
        return []
    console = cast(dict[str, Any], inputs.board.get("console") or {})
    uart = cast(dict[str, Any], console.get("uart") or {})
    if not uart:
        raise InputError(
            f"E console pinos needs console.uart but board "
            f"{inputs.board.get('board')!r} declares none; use console jtag"
        )
    return [
        _scalar(_signal(inputs, str(uart["rx"])), "uart"),
        _scalar(_signal(inputs, str(uart["tx"])), "uart"),
    ]


def _reset_port(
    inputs: BoardInputs, reset: dict[str, Any], io: list[Port]
) -> Port:
    """Monta a porta de reset, ou o apelido de um bit de outra porta.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    reset : dict of {str: Any}
        O `clocks.reset` da placa.
    io : list of Port
        As portas de E/S já montadas.

    Returns
    -------
    Port
        Uma porta com pino próprio, ou com `alias` quando o sinal de
        reset é um bit (`KEY[0]`) de uma porta de E/S.
    """
    name = str(reset["signal"])
    sig = _signal(inputs, name)
    active = str(reset["active"])
    bracket = _BRACKET.match(name)
    if bracket is not None:
        for port in io:
            if port.vector and name in port.bit_names:
                alias = f"{port.name}({bracket.group(2)})"
                return Port(name, "reset", "in", (sig,), False, active, alias)
        name = f"{bracket.group(1)}_{bracket.group(2)}"
    return Port(name, "reset", "in", (sig,), False, active)


def build_ports(inputs: BoardInputs) -> PortPlan:
    """Monta todas as portas do topo de uma plataforma numa placa.

    A ordem é relógio de referência, reset, papéis de E/S, console por
    pinos e memórias de dispositivo.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    PortPlan
        As portas e os avisos.
    """
    clocks = cast(dict[str, Any], inputs.board.get("clocks") or {})
    reference = next(
        c
        for c in cast(list[dict[str, Any]], clocks["inputs"])
        if c["name"] == clocks["reference"]
    )
    reset = cast(dict[str, Any], clocks["reset"])
    io = _io_ports(inputs)
    head = [
        Port(
            str(reference["signal"]),
            "clock",
            "in",
            (_signal(inputs, str(reference["signal"])),),
            False,
        ),
        _reset_port(inputs, reset, list(io.ports)),
    ]
    return PortPlan(
        tuple(head + list(io.ports) + _uart_ports(inputs))
        + tuple(_memory_ports(inputs)),
        io.warnings,
    )


def memory_clock_port(ports: tuple[Port, ...], role: str) -> Port | None:
    """Acha a porta do relógio que sai pelo pino de uma memória.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    role : str
        O tipo da memória.

    Returns
    -------
    Port or None
        A porta escalar de saída cujo nome termina em `CLK`.
    """
    for port in ports:
        if (
            port.role == role
            and not port.vector
            and port.name.upper().endswith("CLK")
        ):
            return port
    return None
