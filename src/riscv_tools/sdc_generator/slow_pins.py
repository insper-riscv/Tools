"""Escreve os caminhos falsos dos pinos lentos de um papel da placa."""

from riscv_tools.board_ports import Port


def slow_pin_lines(ports: tuple[Port, ...], role: str, why: str) -> list[str]:
    """Escreve os caminhos falsos dos pinos de um papel.

    Parameters
    ----------
    ports : tuple of Port
        As portas do topo.
    role : str
        O papel da placa, como `Port.role` o guarda.
    why : str
        O comentário da seção, em uma frase terminada em ponto.

    Returns
    -------
    list of str
        As linhas; vazia sem portas do papel.
    """
    chosen = [p for p in ports if p.role == role]
    if not chosen:
        return []
    lines = ["", f"# {why}"]
    for port in chosen:
        name = f"{port.name}[*]" if port.vector else port.name
        if port.direction in ("in", "inout"):
            lines.append(f"set_false_path -from [get_ports {{{name}}}]")
        if port.direction in ("out", "inout"):
            lines.append(f"set_false_path -to   [get_ports {{{name}}}]")
    return lines
