"""Reúne os dados de uma plataforma e de uma placa para os geradores."""

from riscv_tools.board_inputs.core import (
    BoardInputs,
    InputError,
    PinSignal,
    board_view,
    chip_view,
    family_view,
    load_inputs,
    resolve_board_name,
)

__all__ = [
    "BoardInputs",
    "InputError",
    "PinSignal",
    "board_view",
    "chip_view",
    "family_view",
    "load_inputs",
    "resolve_board_name",
]
