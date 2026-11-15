"""Save a RAM's content to a .mif over JTAG."""

import struct
from collections.abc import Callable, Sequence
from pathlib import Path

from riscv_tools import mem_edit, ram_target, sdram_debug
from riscv_tools.jtag import JtagLink
from riscv_tools.sdram_windows import WORD_BYTES, Window


def dump_ram(
    link: JtagLink,
    ram_mem_instance: ram_target.RamTarget,
    out_mif: Path,
    words: Sequence[int] | None = None,
) -> None:
    """Save the RAM content to a .mif over JTAG.

    Used for memory tests, where the PASS/FAIL result alone isn't
    enough. A RAM inside the FPGA is saved whole (words is not needed).
    A RAM in the SDRAM is too big to read whole over JTAG, so only the
    given words are saved.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to read from.
    ram_mem_instance : int or SdramDebugRam
        How the RAM is reached: the In-System Memory Content Editor
        instance index of the RAM, or SdramDebugRam for a RAM in the
        SDRAM (see ram_target).
    out_mif : Path
        Path to write the .mif to (overwritten if it already exists).
    words : sequence of int, optional
        Word offsets from the base of the RAM to save. Required for
        SdramDebugRam, ignored for a memory instance of the FPGA.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        The RAM is in the SDRAM and no words were given.
    """
    if isinstance(ram_mem_instance, ram_target.SdramDebugRam):
        if words is None:
            raise ValueError(
                "the RAM is the SDRAM: it is too big to dump whole, "
                "give the words to save"
            )
        ram_target.sparse_mif_words(link, ram_mem_instance, words, out_mif)
        return
    mem_edit.dump(link, ram_mem_instance, out_mif)


# Palavras lidas por chamada ao ler uma região inteira; limita o tamanho
# do arquivo de resposta do script.
REGION_CHUNK_WORDS = 1 << 16


def dump_region(
    link: JtagLink,
    window: Window,
    start: int,
    length: int,
    report: Callable[[str], None] | None = None,
) -> bytes:
    """Lê um trecho de uma região da SDRAM, em rajada quando há.

    Parameters
    ----------
    link : JtagLink
        A placa.
    window : Window
        A janela da região (`FLASH` ou `RAM`).
    start : int
        O endereço de byte do SoC do primeiro byte, alinhado a palavra.
    length : int
        Quantos bytes ler, múltiplo de uma palavra.
    report : callable, optional
        Recebe uma linha de progresso por bloco lido.

    Returns
    -------
    bytes
        O conteúdo do trecho, em ordem de endereço.

    Raises
    ------
    ValueError
        Se o trecho não é de palavras ou sai da região.
    """
    if length <= 0 or length % WORD_BYTES:
        raise ValueError("the range must be a positive number of words")
    if not window.contains(start, length):
        raise ValueError(
            f"[0x{start:08x}, 0x{start + length:08x}) is outside "
            f"{window.name} [0x{window.base:08x}, 0x{window.end:08x})"
        )
    first = window.word_address(start)
    total = length // WORD_BYTES
    burst = sdram_debug.capabilities(link).stream_words
    out = bytearray()
    for done in range(0, total, REGION_CHUNK_WORDS):
        count = min(REGION_CHUNK_WORDS, total - done)
        words = sdram_debug.stream_read(link, first + done, count, burst)
        out += struct.pack(f"<{len(words)}I", *words)
        if report is not None:
            report(f"{done + count}/{total} words")
    return bytes(out)


def save_region(out: Path, window: Window, start: int, data: bytes) -> None:
    """Grava o trecho lido, em binário ou em `.mif`.

    Parameters
    ----------
    out : Path
        O arquivo; a extensão `.bin` grava os bytes, qualquer outra
        grava um `.mif` com uma linha por palavra.
    window : Window
        A janela da região.
    start : int
        O endereço de byte do SoC do primeiro byte.
    data : bytes
        O trecho lido.
    """
    if out.suffix == ".bin":
        out.write_bytes(data)
        return
    count = len(data) // WORD_BYTES
    words = struct.unpack(f"<{count}I", data)
    first = (start - window.base) // WORD_BYTES
    lines = [
        "WIDTH=32;",
        f"DEPTH={count};",
        "ADDRESS_RADIX=HEX;",
        "DATA_RADIX=HEX;",
        "CONTENT BEGIN",
        *[f"  {first + i:X} : {w:08X};" for i, w in enumerate(words)],
        "END;",
    ]
    out.write_text("\n".join(lines) + "\n")
