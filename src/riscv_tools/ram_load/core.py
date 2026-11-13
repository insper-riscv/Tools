"""Carrega binários na SDRAM pela porta de debug e dispara o programa.

Cada arquivo é um segmento: bytes que ocupam palavras de 32 bits a
partir de um endereço de byte do mapa de memória. O fluxo é o da carga
de uma imagem grande que um programa do lado da placa espera:

1. A palavra de lançamento (`launch`) é zerada, para que um programa
   que a consulta não parta sobre uma imagem pela metade.
2. Cada segmento é escrito com `sdram_debug.load_words` e lido de volta
   inteiro para a conferência, antes do próximo.
3. Só depois de tudo conferido a magia é escrita em `launch`, sempre por
   último.
"""

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from riscv_tools import sdram_debug
from riscv_tools.jtag import JtagLink

WORD_BYTES = 4
# Palavras lidas por sessão do script ao conferir; limita o tamanho
# da resposta e o número de sessões (uma WAD de 4 MiB leva 17).
VERIFY_CHUNK_WORDS = 1 << 16
_WORD_MASK = 0xFFFFFFFF


class LoadError(ValueError):
    """O pedido é inválido (endereço, tamanho ou sobreposição)."""


class VerifyError(RuntimeError):
    """A leitura de volta difere do que foi escrito."""


@dataclass(frozen=True)
class Segment:
    """Um arquivo a carregar e o endereço de byte onde ele começa."""

    name: str
    address: int
    data: bytes

    @property
    def words(self) -> int:
        """Número de palavras ocupadas, com o resto em zero."""
        return -(-len(self.data) // WORD_BYTES)

    @property
    def end(self) -> int:
        """Primeiro endereço de byte depois do último byte ocupado."""
        return self.address + self.words * WORD_BYTES


def _silent(_line: str) -> None:
    """Ignora uma linha de progresso."""


@dataclass(frozen=True)
class LoadOptions:
    """Como a carga se comporta além dos segmentos."""

    # Tamanho da SDRAM em bytes, para os limites (None não limita).
    ram_bytes: int | None = None
    # Lê cada segmento de volta antes de seguir.
    verify: bool = True
    # Recebe uma linha de progresso por etapa.
    report: Callable[[str], None] = _silent


@dataclass(frozen=True)
class Launch:
    """A palavra que avisa o programa da placa que a carga terminou."""

    address: int
    magic: int


def segment_from_file(name: str, path: Path, address: int) -> Segment:
    """Lê um arquivo como segmento.

    Parameters
    ----------
    name : str
        Nome do segmento nas mensagens.
    path : Path
        O arquivo.
    address : int
        Endereço de byte onde o primeiro byte do arquivo fica.

    Returns
    -------
    Segment
        O segmento.
    """
    return Segment(name, address, path.read_bytes())


def pack_words(data: bytes) -> list[int]:
    """Empacota bytes em palavras little-endian, completando com zeros.

    Parameters
    ----------
    data : bytes
        Os bytes do arquivo.

    Returns
    -------
    list of int
        As palavras de 32 bits, em ordem de endereço.
    """
    padded = data + bytes(-len(data) % WORD_BYTES)
    return list(struct.unpack(f"<{len(padded) // WORD_BYTES}I", padded))


def _check_segment(
    segment: Segment, ram_base: int, ram_bytes: int | None
) -> None:
    """Confere o alinhamento e os limites de um segmento.

    Parameters
    ----------
    segment : Segment
        O segmento.
    ram_base : int
        Endereço de byte da base da SDRAM.
    ram_bytes : int or None
        Tamanho da SDRAM em bytes, ou `None` para não limitar.

    Raises
    ------
    LoadError
        O endereço não é de palavra, o segmento é vazio ou sai da SDRAM.
    """
    if segment.address % WORD_BYTES:
        raise LoadError(
            f"{segment.name}: o endereço 0x{segment.address:08x} "
            "não é alinhado a palavra"
        )
    if not segment.data:
        raise LoadError(f"{segment.name}: o arquivo está vazio")
    if segment.address < ram_base:
        raise LoadError(
            f"{segment.name}: o endereço 0x{segment.address:08x} "
            f"fica abaixo da SDRAM (0x{ram_base:08x})"
        )
    if ram_bytes is not None and segment.end > ram_base + ram_bytes:
        raise LoadError(
            f"{segment.name}: termina em 0x{segment.end:08x}, "
            f"depois do fim da SDRAM (0x{ram_base + ram_bytes:08x})"
        )


def check_layout(
    segments: Sequence[Segment],
    ram_base: int,
    ram_bytes: int | None,
    launch: Launch | None,
) -> None:
    """Confere que os segmentos cabem na SDRAM e não se sobrepõem.

    Parameters
    ----------
    segments : sequence of Segment
        Os segmentos da carga.
    ram_base : int
        Endereço de byte da base da SDRAM.
    ram_bytes : int or None
        Tamanho da SDRAM em bytes, ou `None` para não limitar.
    launch : Launch or None
        A palavra de lançamento; nenhum segmento pode cobri-la.

    Raises
    ------
    LoadError
        Algum segmento é inválido, dois se sobrepõem ou um cobre a
        palavra de lançamento.
    """
    for segment in segments:
        _check_segment(segment, ram_base, ram_bytes)
    ordered = sorted(segments, key=lambda s: s.address)
    for first, second in pairwise(ordered):
        if second.address < first.end:
            raise LoadError(
                f"{first.name} (até 0x{first.end:08x}) e {second.name} "
                f"(desde 0x{second.address:08x}) se sobrepõem"
            )
    if launch is None:
        return
    if launch.address % WORD_BYTES:
        raise LoadError(
            f"a palavra de lançamento 0x{launch.address:08x} "
            "não é alinhada a palavra"
        )
    for segment in segments:
        if segment.address <= launch.address < segment.end:
            raise LoadError(
                f"{segment.name} cobre a palavra de lançamento "
                f"0x{launch.address:08x}"
            )


def _word_address(address: int, ram_base: int) -> int:
    """Converta um endereço de byte em endereço de palavra da SDRAM."""
    return (address - ram_base) // WORD_BYTES


def verify_segment(
    link: JtagLink,
    segment: Segment,
    ram_base: int,
    expected: Sequence[int],
) -> None:
    """Lê o segmento de volta e compara com as palavras escritas.

    Parameters
    ----------
    link : JtagLink
        A placa.
    segment : Segment
        O segmento escrito.
    ram_base : int
        Endereço de byte da base da SDRAM.
    expected : sequence of int
        As palavras que foram escritas.

    Raises
    ------
    VerifyError
        Uma palavra lida difere da escrita; a mensagem dá a primeira.
    """
    first = _word_address(segment.address, ram_base)
    for start in range(0, len(expected), VERIFY_CHUNK_WORDS):
        want = expected[start : start + VERIFY_CHUNK_WORDS]
        got = sdram_debug.read_words(link, first + start, len(want))
        if len(got) != len(want):
            raise VerifyError(
                f"{segment.name}: pediu {len(want)} palavras e vieram "
                f"{len(got)}"
            )
        for offset, (w, g) in enumerate(zip(want, got, strict=True)):
            if w != g & _WORD_MASK:
                address = segment.address + (start + offset) * WORD_BYTES
                raise VerifyError(
                    f"{segment.name}: em 0x{address:08x} escreveu "
                    f"0x{w:08x} e leu 0x{g & _WORD_MASK:08x}"
                )


def load_ram(
    link: JtagLink,
    segments: Sequence[Segment],
    ram_base: int,
    launch: Launch | None,
    options: LoadOptions | None = None,
) -> None:
    """Carrega os segmentos na SDRAM e escreve a magia por último.

    Parameters
    ----------
    link : JtagLink
        A placa.
    segments : sequence of Segment
        Os arquivos e seus endereços.
    ram_base : int
        Endereço de byte da base da SDRAM.
    launch : Launch or None
        A palavra de lançamento; `None` carrega sem disparar.
    options : LoadOptions, optional
        Limite da SDRAM, conferência e progresso; os padrões conferem
        sem limitar.

    Raises
    ------
    LoadError
        O pedido é inválido (nada foi escrito).
    VerifyError
        A conferência falhou; a magia não foi escrita.
    """
    chosen = options or LoadOptions()
    verify, say = chosen.verify, chosen.report
    check_layout(segments, ram_base, chosen.ram_bytes, launch)
    if launch is not None:
        sdram_debug.write_word(
            link, _word_address(launch.address, ram_base), 0
        )
    for segment in segments:
        words = pack_words(segment.data)
        say(
            f"{segment.name}: {len(words)} palavras em 0x{segment.address:08x}"
        )
        sdram_debug.load_words(
            link, _word_address(segment.address, ram_base), words
        )
        if verify:
            verify_segment(link, segment, ram_base, words)
            say(f"{segment.name}: conferido")
    if launch is not None:
        sdram_debug.write_word(
            link, _word_address(launch.address, ram_base), launch.magic
        )
        say(f"magia 0x{launch.magic:08x} em 0x{launch.address:08x}")
