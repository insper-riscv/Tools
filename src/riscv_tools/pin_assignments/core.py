"""Escreve as atribuições por pino do `.qsf` a partir das portas.

É o único lugar que escreve `set_location_assignment` e as atribuições
por instância dos pinos. Nenhuma atribuição é copiada de um `.qsf`: o
padrão de E/S vem do `pins.yaml`, e as demais derivam do papel da porta.

| Papel | Atribuições derivadas |
| :--- | :--- |
| `sdram` | Registradores nas células de E/S das saídas e entradas |
| `leds`, `display` | Corrente padrão e variação de tensão lenta |
"""

from riscv_tools.board_ports import Port


class PinError(ValueError):
    """Um pino não pode ser atribuído."""


# Papéis de saída lenta, sem requisito de tempo.
_SLOW_ROLES = ("leds", "display")


def _target(port: Port) -> str:
    """Dá o alvo de uma atribuição que vale para a porta inteira.

    Parameters
    ----------
    port : Port
        A porta.

    Returns
    -------
    str
        `NOME[*]` para vetor, ou o nome da porta escalar.
    """
    return f"{port.name}[*]" if port.vector else port.name


def _check(ports: tuple[Port, ...], accept_inferred: bool) -> None:
    """Recusa pino inferido não aceito e pino atribuído duas vezes.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    accept_inferred : bool
        Se o usuário aceitou construir com pino `inferred`.

    Raises
    ------
    PinError
        Se um pino é inferido sem aceite, ou dois sinais usam o mesmo
        pino.
    """
    owner: dict[str, str] = {}
    bits = [
        (bit, sig)
        for port in ports
        if not port.alias
        for bit, sig in zip(port.bit_names, port.signals, strict=True)
    ]
    for bit, sig in bits:
        if sig.confirmed == "inferred" and not accept_inferred:
            raise PinError(
                f"E pin {sig.pin} for {bit} is inferred, not "
                "confirmed; pass --accept-inferred-pins"
            )
        if sig.pin in owner:
            raise PinError(
                f"E pin {sig.pin} is assigned to both {owner[sig.pin]} "
                f"and {bit}"
            )
        owner[sig.pin] = bit


def _registers(port: Port) -> list[str]:
    """Deriva os registradores de E/S de uma porta de SDRAM.

    Parameters
    ----------
    port : Port
        A porta de um papel `sdram`.

    Returns
    -------
    list of str
        As linhas de atribuição; vazio para o relógio que sai pelo pino.
    """
    if port.name.upper().endswith("CLK") and not port.vector:
        return []
    target = _target(port)
    name = "set_instance_assignment -name"
    out: list[str] = []
    if port.direction in ("out", "inout"):
        out.append(f"{name} FAST_OUTPUT_REGISTER ON -to {target}")
    if port.direction == "inout":
        out.append(f"{name} FAST_OUTPUT_ENABLE_REGISTER ON -to {target}")
    if port.direction in ("in", "inout"):
        out.append(f"{name} FAST_INPUT_REGISTER ON -to {target}")
    if port.direction == "inout":
        out.append(f"{name} PAD_TO_INPUT_REGISTER_DELAY 0 -to {target}")
    return out


def _port_lines(port: Port) -> list[str]:
    """Escreve as linhas de uma porta.

    Parameters
    ----------
    port : Port
        A porta.

    Returns
    -------
    list of str
        Posição, padrão de E/S e atribuições derivadas do papel.
    """
    name = "set_instance_assignment -name"
    bits = list(zip(port.bit_names, port.signals, strict=True))
    lines = [f"set_location_assignment PIN_{s.pin} -to {b}" for b, s in bits]
    lines += [f'{name} IO_STANDARD "{s.io_standard}" -to {b}' for b, s in bits]
    if port.role == "sdram":
        lines += _registers(port)
    if port.role in _SLOW_ROLES:
        lines += [
            f"{name} CURRENT_STRENGTH_NEW DEFAULT -to {port.name}",
            f"{name} SLEW_RATE 1 -to {port.name}",
        ]
    return lines


def render_pins(ports: tuple[Port, ...], accept_inferred: bool = False) -> str:
    """Escreve o bloco de pinos do `.qsf`.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo, na ordem em que aparecem.
    accept_inferred : bool, optional
        Aceita construir com pino `inferred`, por padrão False.

    Returns
    -------
    str
        O texto, com um cabeçalho de comentário por porta.

    Raises
    ------
    PinError
        Ver `_check`.
    """
    _check(ports, accept_inferred)
    lines: list[str] = []
    for port in ports:
        if not port.alias:
            lines += ["", f"# {port.role}: {port.name}", *_port_lines(port)]
    return "\n".join(lines) + "\n"
