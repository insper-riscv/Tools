"""O subcomando `load-flash`: grava a FLASH da SDRAM pela JTAG."""

import argparse
import sys
from pathlib import Path

from riscv_tools import flash_image, flash_load, sdram_windows
from riscv_tools.cli.common import jtag_link
from riscv_tools.cli.sdram_window_args import banks_of, windows_of
from riscv_tools.flash_image import HEADER_SIZE
from riscv_tools.settings import load_config


def _image(
    args: argparse.Namespace, bank: tuple[int, int] | None
) -> flash_load.FlashImage:
    """Monta o que gravar a partir dos argumentos.

    Parameters
    ----------
    args : argparse.Namespace
        Usa args.image, args.elf, args.address e args.version.
    bank : tuple of (int, int) or None
        Base e tamanho do banco pedido.

    Returns
    -------
    FlashImage
        O endereço, o conteúdo e o tamanho do cabeçalho.

    Raises
    ------
    flash_load.FlashLoadError
        Se os argumentos não bastam para saber onde gravar.
    """
    if (args.image is None) == (args.elf is None):
        raise flash_load.FlashLoadError("give exactly one of --image, --elf")
    if args.image is not None:
        data = Path(args.image).read_bytes()
        if bank is not None:
            flash_image.verify(data)
            return flash_load.FlashImage(bank[0], data, HEADER_SIZE)
        if args.address is None:
            raise flash_load.FlashLoadError(
                "--image needs --bank or --address"
            )
        return flash_load.FlashImage(args.address, data)
    segments = flash_load.load_segments(Path(args.elf))
    if bank is None:
        if len(segments) != 1:
            raise flash_load.FlashLoadError(
                "an ELF with several segments needs --bank"
            )
        return flash_load.FlashImage(segments[0].address, segments[0].data)
    first, payload = flash_load.flat_binary(segments)
    if first != bank[0] + HEADER_SIZE:
        raise flash_load.FlashLoadError(
            f"the ELF starts at 0x{first:08x}, the program of the bank "
            f"starts at 0x{bank[0] + HEADER_SIZE:08x}"
        )
    packed = flash_image.pack(payload, args.version, bank[1])
    return flash_load.FlashImage(bank[0], packed, HEADER_SIZE)


def cmd_load_flash(args: argparse.Namespace) -> None:
    """Implement `riscv-tools load-flash`.

    Prende o núcleo, grava a imagem na janela da FLASH na SDRAM, confere
    pelo CRC-32 calculado na placa e solta o núcleo.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.platform,
        args.image, args.elf, args.bank, args.address and args.version.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    try:
        window = sdram_windows.window_named(windows_of(args, cfg), "FLASH")
        bank = None
        if args.bank is not None:
            known = banks_of(args, cfg)
            if args.bank not in known:
                raise flash_load.FlashLoadError(
                    f"no bank {args.bank} (banks: {', '.join(known)})"
                )
            bank = known[args.bank]
        image = _image(args, bank)
        flash_load.load_flash(jtag_link(cfg), window, image, report=print)
    except (
        flash_load.FlashLoadError,
        flash_load.ElfError,
        flash_image.ImageError,
        sdram_windows.WindowError,
    ) as error:
        sys.exit(f"load-flash: {error}")
