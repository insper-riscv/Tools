"""Lê os arquivos de dados de uma plataforma e de uma placa."""

from riscv_tools.board_inputs.core import (
    BoardInputs,
    InputError,
    PinSignal,
    board_idcode,
    load_chip,
    load_inputs,
    resolve_board_name,
)

__all__ = [
    "BoardInputs",
    "InputError",
    "PinSignal",
    "board_idcode",
    "load_chip",
    "load_inputs",
    "resolve_board_name",
]
