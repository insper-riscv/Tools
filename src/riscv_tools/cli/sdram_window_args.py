"""Acha a janela da SDRAM e os bancos de um pedido."""

import argparse
from pathlib import Path
from typing import Any

from riscv_tools.board_schema.platform_fields import read_platform_file
from riscv_tools.cli.common import project_root
from riscv_tools.memory_map import banks, evaluate
from riscv_tools.sdram_windows import (
    Window,
    windows_from_config,
    windows_from_platform,
)


def windows_of(
    args: argparse.Namespace, cfg: dict[str, Any]
) -> dict[str, Window]:
    """Dá a tabela de janelas do pedido.

    Parameters
    ----------
    args : argparse.Namespace
        Usa args.platform e args.root.
    cfg : dict of {str: Any}
        A configuração mesclada do projeto.

    Returns
    -------
    dict of {str: Window}
        A tabela do `--platform`, ou a de `memory.sdram_windows`.
    """
    if getattr(args, "platform", None):
        path = project_root(args) / args.platform
        return windows_from_platform(read_platform_file(Path(path)))
    return windows_from_config(cfg)


def banks_of(
    args: argparse.Namespace, cfg: dict[str, Any]
) -> dict[str, tuple[int, int]]:
    """Dá a base e o tamanho de cada banco da FLASH.

    Parameters
    ----------
    args : argparse.Namespace
        Usa args.platform e args.root.
    cfg : dict of {str: Any}
        A configuração mesclada do projeto.

    Returns
    -------
    dict of {str: tuple of (int, int)}
        Base e tamanho de cada banco, do `--platform` ou de
        `flash.banks` da configuração.
    """
    if getattr(args, "platform", None):
        path = project_root(args) / args.platform
        listed = banks.bank_list(read_platform_file(Path(path)))
    else:
        flash: dict[str, Any] = cfg.get("flash") or {}
        listed: list[dict[str, Any]] = list(flash.get("banks") or [])
    return {
        str(bank["name"]): (evaluate(bank["base"]), evaluate(bank["size"]))
        for bank in listed
    }
