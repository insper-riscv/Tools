"""Helpers dos testes dos geradores de placa."""

from dataclasses import replace
from pathlib import Path
from typing import Any

from riscv_tools.board_generate import Generated, GenerateRequest, generate
from riscv_tools.board_inputs import BoardInputs, load_inputs

FIXTURES = Path(__file__).parent / "fixtures" / "multifpga"
BOARDS = FIXTURES / "boards"
CHIPS = FIXTURES / "chips"
BOARD_NAMES = (
    "de0-cv",
    "de2-115",
    "de0-nano",
    "de10-lite",
    "de10-nano",
    "de0-nano-soc",
    "mkr-vidor-4000",
)


def platform_file(name: str) -> Path:
    """Dá o `platform.yaml` de fixture de uma placa."""
    return FIXTURES / "platforms" / f"{name}.yaml"


def inputs_of(name: str) -> BoardInputs:
    """Lê os dados de fixture de uma plataforma na sua placa."""
    return load_inputs(platform_file(name), None, BOARDS, CHIPS)


def generated(name: str, accept: bool = True) -> Generated:
    """Gera o projeto de fixture de uma placa."""
    return generate(
        GenerateRequest(
            platform_file(name),
            None,
            BOARDS,
            CHIPS,
            accept_inferred=accept,
        )
    )


def with_platform(inputs: BoardInputs, **changes: Any) -> BoardInputs:
    """Copia os dados trocando campos do platform.yaml."""
    return replace(inputs, platform=dict(inputs.platform) | changes)
