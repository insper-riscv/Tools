"""A carga da SDRAM (`load-ram`) contra uma SDRAM simulada."""

import sys
from pathlib import Path
from typing import Any

import pytest
from support import check_equal

from riscv_tools import ram_load
from riscv_tools.cli import ram_load_cmd
from riscv_tools.cli.parser import main
from riscv_tools.jtag import JtagLink
from riscv_tools.sdram_debug import core as sdram_core

LINK = JtagLink(hardware_name="cable", device_name="device")
BASE = 0x40000000
LAUNCH = 0x43FFFFF8
MAGIC = 0x4D4F4F44
RAM_BYTES = 0x04000000
OPTIONS = ram_load.LoadOptions(ram_bytes=RAM_BYTES)
GO = ram_load.Launch(LAUNCH, MAGIC)


class FakeSdram:
    """Substitui o run_tcl: uma SDRAM em dicionário com registro."""

    def __init__(self, corrupt_word: int | None = None) -> None:
        """Começa vazia, com uma palavra opcional que sai errada."""
        self.memory: dict[int, int] = {}
        self.events: list[tuple[str, int]] = []
        self.corrupt_word = corrupt_word

    def __call__(self, _link: JtagLink, _script: str, *args: Any) -> Any:
        """Responde a um comando do script como a placa responderia."""
        command = args[0]
        handler = {
            "write": self._write,
            "load": self._load,
            "read": self._read,
        }[command]
        stdout = handler(int(args[1]), args[2])
        self.events.append((command, int(args[1])))
        return type("Completed", (), {"stdout": stdout})()

    def _write(self, first: int, value: Any) -> str:
        """Guarda uma palavra."""
        self.memory[first] = int(value)
        return "OK"

    def _load(self, first: int, path: Any) -> str:
        """Guarda as palavras de um arquivo de texto em hexadecimal."""
        text = Path(path).read_text(encoding="utf-8").split()
        for index, word in enumerate(text):
            self.memory[first + index] = int(word, 16)
        return "OK"

    def _read(self, first: int, count: Any) -> str:
        """Devolve as palavras, com a escolhida errada num bit."""
        values = [
            self.memory.get(first + i, 0)
            ^ (1 if first + i == self.corrupt_word else 0)
            for i in range(int(count))
        ]
        return "WORDS=" + " ".join(str(v) for v in values)

    def kinds(self, command: str) -> list[int]:
        """Dá as posições, no registro, dos eventos de um comando."""
        return [i for i, e in enumerate(self.events) if e[0] == command]


def _install(monkeypatch: pytest.MonkeyPatch, fake: FakeSdram) -> FakeSdram:
    """Põe a SDRAM simulada no lugar do script."""
    monkeypatch.setattr(sdram_core, "run_tcl", fake)
    return fake


def _word(fake: FakeSdram, address: int) -> int:
    """Lê a palavra que está num endereço de byte."""
    return fake.memory.get((address - BASE) // 4, 0)


def test_pack_words_pads_the_tail_with_zeros() -> None:
    """Os bytes viram palavras little-endian, com o resto em zero."""
    check_equal(
        ram_load.pack_words(b"\x01\x02\x03\x04\x05"),
        [0x04030201, 0x00000005],
    )


def test_a_binary_and_a_wad_are_loaded_and_the_magic_comes_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binário e WAD vão a seus endereços e a magia sai por último."""
    fake = _install(monkeypatch, FakeSdram())
    wad_at = BASE + 0x1000
    segments = [
        ram_load.Segment("binary", BASE, b"\x11\x22\x33\x44" * 3),
        ram_load.Segment("wad", wad_at, b"IWAD" + bytes(range(7))),
    ]
    ram_load.load_ram(LINK, segments, BASE, GO, OPTIONS)
    check_equal(_word(fake, BASE), 0x44332211)
    check_equal(_word(fake, BASE + 8), 0x44332211)
    check_equal(_word(fake, wad_at), 0x44415749)
    check_equal(_word(fake, wad_at + 4), 0x03020100)
    check_equal(_word(fake, wad_at + 8), 0x00060504)
    check_equal(_word(fake, LAUNCH), MAGIC)
    magic_word = (LAUNCH - BASE) // 4
    check_equal(
        [e for e in fake.events if e[0] == "write"],
        [("write", magic_word)] * 2,
    )
    check_equal(fake.events[0], ("write", magic_word))
    check_equal(fake.events[-1], ("write", magic_word))
    check_equal(len(fake.kinds("load")), 2)
    check_equal(len(fake.kinds("read")), 2)


def test_a_stale_magic_is_cleared_before_the_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma magia velha em `launch` é zerada antes da carga."""
    fake = _install(monkeypatch, FakeSdram(corrupt_word=0))
    fake.memory[(LAUNCH - BASE) // 4] = MAGIC
    segments = [ram_load.Segment("binary", BASE, b"abcd")]
    with pytest.raises(ram_load.VerifyError):
        ram_load.load_ram(LINK, segments, BASE, GO, OPTIONS)
    check_equal(_word(fake, LAUNCH), 0)


def test_a_read_back_difference_stops_before_the_magic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se a leitura de volta difere, a magia não é escrita."""
    fake = _install(monkeypatch, FakeSdram(corrupt_word=2))
    segments = [ram_load.Segment("wad", BASE, bytes(range(16)))]
    with pytest.raises(ram_load.VerifyError, match="0x40000008"):
        ram_load.load_ram(LINK, segments, BASE, GO, OPTIONS)
    check_equal(_word(fake, LAUNCH), 0)


def test_no_launch_writes_no_magic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem `launch`, só os segmentos são escritos."""
    fake = _install(monkeypatch, FakeSdram())
    segments = [ram_load.Segment("binary", BASE, b"abcd")]
    ram_load.load_ram(LINK, segments, BASE, None)
    check_equal(fake.kinds("write"), [])


def test_no_verify_skips_the_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Com a conferência desligada nenhuma leitura é feita."""
    fake = _install(monkeypatch, FakeSdram())
    segments = [ram_load.Segment("binary", BASE, b"abcd")]
    options = ram_load.LoadOptions(verify=False)
    ram_load.load_ram(LINK, segments, BASE, None, options)
    check_equal(fake.kinds("read"), [])


@pytest.mark.parametrize(
    ("segments", "text"),
    [
        ([ram_load.Segment("a", BASE + 2, b"abcd")], "alinhado"),
        ([ram_load.Segment("a", BASE, b"")], "vazio"),
        ([ram_load.Segment("a", BASE - 4, b"abcd")], "abaixo"),
        (
            [ram_load.Segment("a", BASE + RAM_BYTES - 4, b"abcdefgh")],
            "depois do fim",
        ),
        (
            [
                ram_load.Segment("a", BASE, bytes(16)),
                ram_load.Segment("b", BASE + 8, bytes(16)),
            ],
            "sobrepõem",
        ),
        (
            [ram_load.Segment("a", LAUNCH - 4, bytes(8))],
            "palavra de lançamento",
        ),
    ],
)
def test_an_invalid_layout_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    segments: list[ram_load.Segment],
    text: str,
) -> None:
    """Um pedido inválido é recusado antes de qualquer escrita."""
    fake = _install(monkeypatch, FakeSdram())
    with pytest.raises(ram_load.LoadError, match=text):
        ram_load.load_ram(LINK, segments, BASE, GO, OPTIONS)
    check_equal(fake.events, [])


def test_a_wad_of_the_real_size_is_read_back_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma WAD de 4.196.020 bytes é lida de volta em blocos."""
    fake = _install(monkeypatch, FakeSdram())
    size = 4_196_020
    data = bytes(i * 7 & 0xFF for i in range(size))
    wad_at = BASE + 0x00080000
    segments = [ram_load.Segment("wad", wad_at, data)]
    ram_load.load_ram(LINK, segments, BASE, GO, OPTIONS)
    # 1.049.005 palavras em blocos de 65.536
    check_equal(len(fake.kinds("read")), 17)
    check_equal(
        _word(fake, wad_at + size - 4), int.from_bytes(data[-4:], "little")
    )


def _link(_cfg: dict[str, Any]) -> JtagLink:
    """Dá a placa de teste no lugar da detecção do cabo."""
    return LINK


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str
) -> int:
    """Roda `riscv-tools load-ram` sobre uma configuração mínima."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "memory:\n"
        f"  ram_base: {BASE}\n"
        f"  ram_words: {RAM_BYTES // 4}\n"
        f"  launch_addr: {LAUNCH}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ram_load_cmd, "jtag_link", _link)
    monkeypatch.setattr(
        sys,
        "argv",
        ["riscv-tools", "--config", str(config), "load-ram", *argv],
    )
    try:
        main()
    except SystemExit as stop:
        return 1 if isinstance(stop.code, str) else int(stop.code or 0)
    return 0


def test_the_command_loads_a_binary_and_a_wad(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O subcomando usa a base e a palavra `launch` do mapa."""
    fake = _install(monkeypatch, FakeSdram())
    binary = tmp_path / "doom.bin"
    binary.write_bytes(b"\x01\x00\x00\x00")
    wad = tmp_path / "doom1.wad"
    wad.write_bytes(b"IWAD")
    code = _run_cli(
        monkeypatch,
        tmp_path,
        str(binary),
        "--wad",
        str(wad),
        "--wad-address",
        "0x40100000",
    )
    check_equal(code, 0)
    check_equal(_word(fake, BASE), 1)
    check_equal(_word(fake, 0x40100000), 0x44415749)
    check_equal(_word(fake, LAUNCH), MAGIC)


def test_the_command_needs_the_wad_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--wad` sem `--wad-address` é recusado sem escrever."""
    fake = _install(monkeypatch, FakeSdram())
    binary = tmp_path / "doom.bin"
    binary.write_bytes(b"abcd")
    code = _run_cli(monkeypatch, tmp_path, str(binary), "--wad", str(binary))
    check_equal(code, 1)
    check_equal(fake.events, [])
