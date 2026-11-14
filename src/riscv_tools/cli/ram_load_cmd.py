"""O subcomando `load-ram`: carrega arquivos na SDRAM e dispara."""

import argparse
import sys
from pathlib import Path
from typing import Any

from riscv_tools import ram_load
from riscv_tools.cli.common import jtag_link
from riscv_tools.settings import load_config

DEFAULT_MAGIC = 0x4D4F4F44


def _launch(args: argparse.Namespace, memory: dict[str, Any]) -> Any:
    """Decide a palavra de lançamento do pedido.

    Parameters
    ----------
    args : argparse.Namespace
        Usa args.no_launch, args.launch_address e args.magic.
    memory : dict of {str: Any}
        A seção `memory` da configuração, de onde vem `launch_addr`.

    Returns
    -------
    Launch or None
        A palavra de lançamento, ou `None` com `--no-launch`.
    """
    if args.no_launch:
        return None
    address = args.launch_address
    if address is None:
        address = memory.get("launch_addr")
    if address is None:
        sys.exit(
            "load-ram: o mapa não reserva `launch`; passe "
            "--launch-address ou --no-launch"
        )
    return ram_load.Launch(address=int(address), magic=args.magic)


def _segments(args: argparse.Namespace, base: int) -> list[Any]:
    """Monta os segmentos do pedido.

    Parameters
    ----------
    args : argparse.Namespace
        Usa args.binary, args.address, args.wad e args.wad_address.
    base : int
        Base da SDRAM, o endereço padrão do binário.

    Returns
    -------
    list of Segment
        O binário e, quando dado, a WAD.
    """
    address = base if args.address is None else args.address
    segments = [
        ram_load.segment_from_file("binary", Path(args.binary), address)
    ]
    if args.wad is not None:
        if args.wad_address is None:
            sys.exit("load-ram: --wad exige --wad-address")
        segments.append(
            ram_load.segment_from_file("wad", Path(args.wad), args.wad_address)
        )
    return segments


def cmd_load_ram(args: argparse.Namespace) -> None:
    """Implement `riscv-tools load-ram`.

    Carrega o binário (e a WAD) na SDRAM pela porta de debug, confere
    por leitura de volta e escreve a magia em `launch` por último.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.binary,
        args.address, args.wad, args.wad_address, args.launch_address,
        args.magic, args.no_launch e args.no_verify.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    memory = cfg.get("memory", {})
    base = int(memory["ram_base"])
    words = memory.get("ram_words")
    segments = _segments(args, base)
    launch = _launch(args, memory)
    link = jtag_link(cfg)
    try:
        ram_load.load_ram(
            link,
            segments,
            base,
            launch,
            ram_load.LoadOptions(
                ram_bytes=None if words is None else int(words) * 4,
                verify=not args.no_verify,
                report=print,
            ),
        )
    except (ram_load.LoadError, ram_load.VerifyError) as error:
        sys.exit(f"load-ram: {error}")
