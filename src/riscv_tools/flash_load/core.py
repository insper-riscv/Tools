"""Grava a FLASH na SDRAM pela porta de depuração, com o núcleo preso.

O fluxo de uma gravação é o do `load-flash`.

1. O bitstream precisa ter `hold` e CRC (`capabilities`); sem
   eles a gravação é recusada, porque o núcleo e a JTAG escreveriam a
   FLASH ao mesmo tempo e as caches guardariam linhas antigas.
2. O núcleo é preso em reset. O reset da cache de instruções limpa as
   linhas válidas, então o núcleo que sai do reset busca da SDRAM.
3. O conteúdo é escrito em rajada. Os primeiros `header_size` bytes (o
   cabeçalho de um banco) vão por último, para uma gravação interrompida
   deixar um banco que a BOOT não valida.
4. O CRC-32 do trecho, calculado na placa, é comparado com o do arquivo.
5. O núcleo é solto, mesmo quando a conferência falha: a BOOT valida os
   bancos e salta para o que estiver íntegro.
"""

import zlib
from collections.abc import Callable
from dataclasses import dataclass

from riscv_tools import sdram_debug
from riscv_tools.jtag import JtagLink
from riscv_tools.ram_load import pack_words
from riscv_tools.sdram_windows import Window

WORD_BYTES = 4
_PAD = 0xFF


class FlashLoadError(RuntimeError):
    """A gravação foi recusada ou a conferência falhou."""


def _silent(_line: str) -> None:
    """Ignora uma linha de progresso."""


@dataclass(frozen=True)
class FlashImage:
    """O que gravar e onde.

    Parameters
    ----------
    address : int
        O endereço de byte do SoC do primeiro byte.
    data : bytes
        O conteúdo; é completado com 0xFF até uma palavra.
    header_size : int, optional
        Bytes iniciais que vão por último (o cabeçalho de um banco).
    """

    address: int
    data: bytes
    header_size: int = 0


def _padded(data: bytes) -> bytes:
    """Completa os bytes até uma palavra inteira com 0xFF.

    Parameters
    ----------
    data : bytes
        O conteúdo.

    Returns
    -------
    bytes
        O conteúdo, com `0xFF` no fim se faltava para a palavra.
    """
    return data + bytes([_PAD]) * (-len(data) % WORD_BYTES)


def check_request(window: Window, image: FlashImage) -> None:
    """Confere o pedido antes de tocar na placa.

    Parameters
    ----------
    window : Window
        A janela da FLASH.
    image : FlashImage
        O que gravar.

    Raises
    ------
    FlashLoadError
        Se o conteúdo é vazio, o endereço não é de palavra, o cabeçalho
        é maior que o conteúdo ou o trecho sai da FLASH.
    """
    size = len(_padded(image.data))
    if not image.data:
        raise FlashLoadError("the image is empty")
    if image.address % WORD_BYTES or image.header_size % WORD_BYTES:
        raise FlashLoadError("the address and the header must be words")
    if image.header_size > size:
        raise FlashLoadError("the header is larger than the image")
    if not window.contains(image.address, size):
        raise FlashLoadError(
            f"0x{image.address:08x} + {size} bytes is outside the FLASH "
            f"[0x{window.base:08x}, 0x{window.end:08x})"
        )


def _write_order(
    window: Window, image: FlashImage
) -> list[tuple[int, list[int]]]:
    """Dá os trechos a escrever, com o cabeçalho por último.

    Parameters
    ----------
    window : Window
        A janela da FLASH.
    image : FlashImage
        O que gravar.

    Returns
    -------
    list of tuple of (int, list of int)
        O endereço de palavra do chip e as palavras de cada trecho.
    """
    words = pack_words(_padded(image.data))
    head = image.header_size // WORD_BYTES
    first = window.word_address(image.address)
    parts = [(first + head, words[head:]), (first, words[:head])]
    return [(address, chunk) for address, chunk in parts if chunk]


def load_flash(
    link: JtagLink,
    window: Window,
    image: FlashImage,
    report: Callable[[str], None] = _silent,
) -> int:
    """Grava a imagem na FLASH, confere pelo CRC e solta o núcleo.

    Parameters
    ----------
    link : JtagLink
        A placa.
    window : Window
        A janela da FLASH.
    image : FlashImage
        O que gravar.
    report : callable, optional
        Recebe uma linha de progresso por etapa.

    Returns
    -------
    int
        O CRC-32 que a placa calculou, igual ao do conteúdo.

    Raises
    ------
    FlashLoadError
        Se o pedido é inválido, o bitstream não tem `hold` e CRC ou o
        CRC da placa difere do do conteúdo.
    """
    check_request(window, image)
    caps = sdram_debug.capabilities(link)
    if not caps.can_load_flash:
        raise FlashLoadError(
            "this bitstream has no hold and CRC in the SDRAM debug port; "
            "the FLASH is not written while the core can run"
        )
    padded = _padded(image.data)
    expected = zlib.crc32(padded) & 0xFFFFFFFF
    first = window.word_address(image.address)
    sdram_debug.set_hold(link, True)
    try:
        for address, chunk in _write_order(window, image):
            report(f"writing {len(chunk)} words at word 0x{address:x}")
            sdram_debug.stream_write(link, address, chunk, caps.stream_words)
        got = sdram_debug.crc32(link, first, len(padded) // WORD_BYTES)
    finally:
        sdram_debug.set_hold(link, False)
    if got != expected:
        raise FlashLoadError(
            f"CRC-32 of the board is 0x{got:08x}, the image has "
            f"0x{expected:08x}"
        )
    report(f"CRC-32 0x{got:08x} checked, core released")
    return got
