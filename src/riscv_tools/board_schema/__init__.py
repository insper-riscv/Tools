"""Read and check the board, family, chip and pins catalog files."""

from riscv_tools.board_schema.board import parse_board
from riscv_tools.board_schema.catalog import Catalog, NotFoundError
from riscv_tools.board_schema.chip import parse_chip
from riscv_tools.board_schema.family import parse_family
from riscv_tools.board_schema.fields import SchemaError
from riscv_tools.board_schema.model import (
    Board,
    Chip,
    Family,
    IoRole,
    Pin,
)
from riscv_tools.board_schema.pins import (
    expand_group,
    group_count,
    parse_pins,
)
from riscv_tools.board_schema.platform_fields import (
    IoNeed,
    PlatformBoardFields,
    declares_board,
    parse_platform_fields,
)

__all__ = [
    "Board",
    "Catalog",
    "Chip",
    "Family",
    "IoNeed",
    "IoRole",
    "NotFoundError",
    "Pin",
    "PlatformBoardFields",
    "SchemaError",
    "declares_board",
    "expand_group",
    "group_count",
    "parse_board",
    "parse_chip",
    "parse_family",
    "parse_pins",
    "parse_platform_fields",
]
