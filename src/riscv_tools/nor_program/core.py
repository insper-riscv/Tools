"""Escreve uma banca da FLASH NOR por um programa deixado na SDRAM.

A NOR não tem carregador de JTAG: o chip só muda pelos comandos do
controlador de FLASH que um programa do núcleo emite. O hospedeiro
deixa na SDRAM, pela porta de depuração, o programador
(`paths.nor_programmer`, ligado na SDRAM), o trabalho (banca, tamanho)
e a imagem, e escreve a entrada de RAM do BOOT_MEMORY (magia e entrada
nos 8 últimos bytes da RAM). O núcleo reinicia, roda o programador, que
apaga e grava a banca e para em `rv32_wait_restart`.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools import htif, ram_target, sdram_debug
from riscv_tools.compiler.build import C_STANDARD_FLAGS, elf_to_bin, run_gcc
from riscv_tools.jtag import JtagLink

# 'RAMB': a magia da entrada de RAM do BOOT_MEMORY.
RAM_BOOT_MAGIC = 0x52414D42
# 'NROP': a magia do trabalho que o programador lê.
JOB_MAGIC = 0x504F524E
_WORD = 4
# O buffer de stdout fica 1 KiB + 8 bytes antes de tohost.
_STDOUT_BYTES = 1024 + 8
_PROGRAM_OFFSET = 0x00100000
_DATA_OFFSET = 0x00200000
_JOB_OFFSET = 0x01000000 - 32
_IMAGE_OFFSET = 0x01000000
_PAGE = 256
_HEADER_PAYLOAD_WORD = 1
_HEADER_BYTES = 256


@dataclass(frozen=True)
class Layout:
    """Onde cada coisa fica na RAM durante a gravação.

    Attributes
    ----------
    program : int
        Endereço de byte onde o programador é ligado e carregado.
    data : int
        Início da RAM que o programador usa para dados e pilha.
    data_size : int
        Tamanho dessa RAM, até o buffer de stdout.
    job : int
        Endereço do trabalho (magia, destino, tamanho, flags).
    image : int
        Endereço da imagem da banca.
    ram_end : int
        Fim da RAM; a entrada de RAM do BOOT_MEMORY ocupa os 8 últimos
        bytes.
    """

    program: int
    data: int
    data_size: int
    job: int
    image: int
    ram_end: int


def layout_of(cfg: dict[str, Any]) -> Layout:
    """Calcula o mapa da gravação a partir do mapa da plataforma.

    Parameters
    ----------
    cfg : dict of {str: Any}
        A configuração mesclada: usa `memory.ram_base`, `ram_words` e
        `tohost_addr`.

    Returns
    -------
    Layout
        Os endereços.
    """
    memory = cfg["memory"]
    base = int(memory["ram_base"])
    stdout = int(memory["tohost_addr"]) - _STDOUT_BYTES
    return Layout(
        program=base + _PROGRAM_OFFSET,
        data=base + _DATA_OFFSET,
        data_size=stdout - (base + _DATA_OFFSET),
        job=base + _JOB_OFFSET,
        image=base + _IMAGE_OFFSET,
        ram_end=base + int(memory["ram_words"]) * _WORD,
    )


def build_programmer(cfg: dict[str, Any], root: Path, build_dir: Path) -> Path:
    """Compila o programador, ligado na SDRAM, e guarda a entrada dele.

    Parameters
    ----------
    cfg : dict of {str: Any}
        A configuração mesclada: usa `paths.nor_programmer`,
        `paths.sources`,
        `paths.include_dir`, `toolchain` e `memory`.
    root : Path
        A raiz do projeto.
    build_dir : Path
        Onde escrever `nor_programmer.elf`, `.bin` e `.json`.

    Returns
    -------
    Path
        O `.bin` do programador.
    """
    layout = layout_of(cfg)
    toolchain = cfg["toolchain"]
    paths = cfg["paths"]
    build_dir.mkdir(parents=True, exist_ok=True)
    elf = build_dir / "nor_programmer.elf"
    run_gcc(
        toolchain,
        [
            "-march=rv32im_zifencei",
            "-mabi=ilp32",
            "-Os",
            *C_STANDARD_FLAGS,
            f"--specs={root / toolchain['specs']}",
            f"-I{root / paths['include_dir']}",
            f"-DNOR_JOB_ADDR={layout.job:#x}u",
            f"-DNOR_IMAGE_ADDR={layout.image:#x}u",
            # o último --defsym vale: estes trocam a FLASH pelo programa
            # na SDRAM e a RAM pela região de dados
            f"-Wl,--defsym=__flash={layout.program:#x}",
            f"-Wl,--defsym=__flash_size={layout.data - layout.program:#x}",
            f"-Wl,--defsym=__ram={layout.data:#x}",
            f"-Wl,--defsym=__ram_size={layout.data_size:#x}",
            *[str(root / source) for source in paths["sources"]],
            str(root / paths["nor_programmer"]),
            "-o",
            str(elf),
        ],
    )
    binary = elf.with_suffix(".bin")
    elf_to_bin(toolchain, elf, binary)
    entry = subprocess.run(
        [toolchain["nm"], str(elf)], capture_output=True, text=True, check=True
    )
    start = next(
        int(line.split()[0], 16)
        for line in entry.stdout.splitlines()
        if line.endswith(" _start")
    )
    (build_dir / "nor_programmer.json").write_text(
        json.dumps({"entry": start}), encoding="utf-8"
    )
    return binary


def load_bank_image(words: list[int], rom_base: int) -> bytes:
    """Extrai a imagem da banca de um `.mif` do FLASH.

    Parameters
    ----------
    words : list of int
        As palavras do FLASH desde o endereço 0.
    rom_base : int
        O endereço do início da região FLASH, onde a banca A começa.

    Returns
    -------
    bytes
        A página de cabeçalho e o payload, em páginas inteiras.

    Raises
    ------
    ValueError
        Se o FLASH não traz o cabeçalho de uma imagem.
    """
    first = rom_base // _WORD
    if len(words) <= first + _HEADER_PAYLOAD_WORD:
        raise ValueError("the FLASH image has no header page")
    size = words[first + _HEADER_PAYLOAD_WORD]
    used = _HEADER_BYTES + size
    data = b"".join(
        w.to_bytes(_WORD, "little")
        for w in words[first : first + -(-used // _WORD)]
    )[:used]
    # O resto da página fica em 0xFF, que a gravação pula.
    return data + b"\xff" * (-len(data) % _PAGE)


def words_of(data: bytes) -> list[int]:
    """Palavras de 32 bits de um bloco, completado com 0xFF."""
    padded = data + b"\xff" * (-len(data) % _WORD)
    return [
        int.from_bytes(padded[i : i + _WORD], "little")
        for i in range(0, len(padded), _WORD)
    ]


def program_bank(
    link: JtagLink,
    cfg: dict[str, Any],
    programmer: Path,
    job: tuple[bytes, int],
    timeout_s: float = 600.0,
) -> int:
    """Grava uma banca da NOR e para o núcleo em `rv32_wait_restart`.

    Parameters
    ----------
    link : JtagLink
        A placa.
    cfg : dict of {str: Any}
        A configuração mesclada.
    programmer : Path
        O `.bin` do programador (`build_programmer`); a entrada fica em
        `nor_programmer.json` ao lado.
    job : tuple of (bytes, int)
        A imagem da banca (página de cabeçalho primeiro) e o endereço de
        byte da banca.
    timeout_s : float, optional
        Quanto esperar pelo programador.

    Returns
    -------
    int
        O `tohost` ao fim: 1 é sucesso.
    """
    image, dest = job
    layout = layout_of(cfg)
    memory = cfg["memory"]
    base = int(memory["ram_base"])
    entry = json.loads(
        programmer.with_suffix(".json").read_text(encoding="utf-8")
    )["entry"]
    sdram_debug.load_words(
        link,
        (layout.program - base) // _WORD,
        words_of(programmer.read_bytes()),
    )
    sdram_debug.load_words(
        link, (layout.image - base) // _WORD, words_of(image)
    )
    sdram_debug.load_words(
        link,
        (layout.job - base) // _WORD,
        [JOB_MAGIC, dest, len(image), 0],
    )
    target = ram_target.target_from_config(cfg, link)
    entry_word = (layout.ram_end - base) // _WORD
    ram_target.write_word(link, target, entry_word - 1, entry)
    ram_target.write_word(link, target, entry_word - 2, RAM_BOOT_MAGIC)
    htif.clear_tohost_configured(link, cfg)
    htif.pulse_fromhost_configured(link, cfg)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = htif.read_tohost_configured(link, cfg)
        if htif.is_done(value):
            return value
        time.sleep(2.0)
    raise TimeoutError("the NOR programmer did not finish")
