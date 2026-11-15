"""Hold, CRC e rajada da porta de depuração da SDRAM.

Estas operações exigem o bitstream com o contrato descrito em
`docs/pt-br/modules/sdram_debug.md` (seção "Contrato com o Memory").
`capabilities` diz o que o bitstream tem; as demais funções recusam o
que ele não tem, sem tentar uma alternativa que escreva a FLASH sem o
`hold`.
"""

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from riscv_tools.jtag import JtagLink, run_tcl
from riscv_tools.sdram_debug.core import load_words, read_words

_STREAM_TCL = "sdram_stream.tcl"
_WORD_MASK = 0xFFFFFFFF
# Campos da palavra de capacidades (subcomando INFO do `op` 7).
_STREAM_SHIFT = 8
_STREAM_MASK = 0xFF
_HOLD_BIT = 16
_CRC_BIT = 17


class StreamError(RuntimeError):
    """O bitstream não tem a operação pedida ou respondeu errado."""


@dataclass(frozen=True)
class Capabilities:
    """O que o mestre de depuração do bitstream sabe fazer.

    Parameters
    ----------
    stream_words : int
        Palavras por deslocamento da rajada; 0 sem rajada.
    hold : bool
        Existe o `hold` do núcleo.
    crc : bool
        Existe o CRC-32 calculado na placa.
    """

    stream_words: int
    hold: bool
    crc: bool

    @property
    def can_load_flash(self) -> bool:
        """Diz se o bitstream deixa carregar a FLASH com segurança.

        Returns
        -------
        bool
            True com `hold` e CRC, as duas condições do `load-flash`.
        """
        return self.hold and self.crc


def decode_capabilities(word: int) -> Capabilities:
    """Lê a palavra de capacidades.

    Parameters
    ----------
    word : int
        A resposta do subcomando INFO.

    Returns
    -------
    Capabilities
        Os campos da palavra.
    """
    return Capabilities(
        stream_words=(word >> _STREAM_SHIFT) & _STREAM_MASK,
        hold=bool(word >> _HOLD_BIT & 1),
        crc=bool(word >> _CRC_BIT & 1),
    )


def _reply(link: JtagLink, prefix: str, *args: object) -> str:
    """Roda um comando do script e devolve o valor da linha de resposta.

    Parameters
    ----------
    link : JtagLink
        A placa.
    prefix : str
        O início da linha de resposta (`INFO=`, `CRC=`).
    *args : object
        O comando e seus argumentos.

    Returns
    -------
    str
        O texto depois do `=`.

    Raises
    ------
    StreamError
        O script não imprimiu a linha.
    """
    result = run_tcl(link, _STREAM_TCL, *args)
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    raise StreamError(f"{_STREAM_TCL} sem a linha {prefix}:\n{result.stdout}")


def capabilities(link: JtagLink) -> Capabilities:
    """Pergunta ao bitstream o que ele sabe fazer.

    Parameters
    ----------
    link : JtagLink
        A placa.

    Returns
    -------
    Capabilities
        As capacidades; tudo ausente num bitstream sem o contrato.
    """
    return decode_capabilities(int(_reply(link, "INFO=", "info"), 16))


def set_hold(link: JtagLink, hold: bool) -> None:
    """Prende ou solta o núcleo em reset.

    Parameters
    ----------
    link : JtagLink
        A placa.
    hold : bool
        True prende o núcleo; False o solta.
    """
    run_tcl(link, _STREAM_TCL, "hold", int(hold))


def crc32(link: JtagLink, word_address: int, word_count: int) -> int:
    """Pede o CRC-32 de um trecho da SDRAM, calculado na placa.

    O CRC é o `zlib.crc32` dos bytes do trecho em ordem de endereço,
    cada palavra em little-endian.

    Parameters
    ----------
    link : JtagLink
        A placa.
    word_address : int
        Endereço de palavra do chip onde o trecho começa.
    word_count : int
        Palavras do trecho.

    Returns
    -------
    int
        O CRC-32 sem sinal.
    """
    text = _reply(link, "CRC=", "crc", word_address, word_count)
    return int(text, 16) & _WORD_MASK


def stream_write(
    link: JtagLink, word_address: int, words: Sequence[int], burst: int
) -> None:
    """Escreve palavras consecutivas em rajada.

    O que não completa uma rajada inteira vai palavra a palavra, para a
    escrita nunca passar do fim pedido.

    Parameters
    ----------
    link : JtagLink
        A placa.
    word_address : int
        Endereço de palavra do chip da primeira palavra.
    words : sequence of int
        As palavras, em ordem de endereço.
    burst : int
        Palavras por deslocamento (`Capabilities.stream_words`); 0 faz
        tudo palavra a palavra.
    """
    bulk = (len(words) // burst) * burst if burst else 0
    if bulk:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image.txt"
            image.write_text(
                "".join(f"{w & _WORD_MASK:08x}\n" for w in words[:bulk])
            )
            run_tcl(link, _STREAM_TCL, "streamwrite", word_address, image)
    if bulk < len(words):
        load_words(link, word_address + bulk, words[bulk:])


def stream_read(
    link: JtagLink, word_address: int, word_count: int, burst: int
) -> list[int]:
    """Lê palavras consecutivas em rajada.

    Parameters
    ----------
    link : JtagLink
        A placa.
    word_address : int
        Endereço de palavra do chip da primeira palavra.
    word_count : int
        Quantas palavras ler.
    burst : int
        Palavras por deslocamento; 0 lê palavra a palavra.

    Returns
    -------
    list of int
        As palavras lidas, em ordem de endereço.
    """
    bulk = (word_count // burst) * burst if burst else 0
    words: list[int] = []
    if bulk:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.txt"
            run_tcl(link, _STREAM_TCL, "streamread", word_address, bulk, out)
            words = [int(t, 16) for t in out.read_text().split()]
    if bulk < word_count:
        words += read_words(link, word_address + bulk, word_count - bulk)
    return words
