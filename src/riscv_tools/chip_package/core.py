"""Do catálogo de chips para o pacote VHDL e para os atrasos do `.sdc`.

Os tempos de um chip existem só no seu arquivo do catálogo. O pacote
gerado leva os mesmos nomes de constante que o `sdram_pkg.vhd` tem
hoje (`T_CK_PS`, `T_RCD_PS`, ...), de modo que a troca do pacote
escrito à mão por este é uma troca de `use`. O `.sdc` recebe os atrasos
de E/S pela função `chip_io_delays`.
"""

import math
import re
from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.board_inputs import InputError

_GROUP_FROM = 100_000
_MODE_WIDTH = 7
_SDRAM_REQUIRED = (
    "tck_ps",
    "trcd_ps",
    "trp_ps",
    "tras_ps",
    "trc_ps",
    "trfc_ps",
    "twr_ps",
    "tmrd_ck",
    "tinit_ps",
    "trefi_ps",
    "init_refreshes",
)
_COMMENTS = {
    "T_CK_PS": "Período do clock que as contagens de ciclos assumem.",
    "T_RCD_PS": "ACTIVE até READ/WRITE.",
    "T_RP_PS": "PRECHARGE até ACTIVE.",
    "T_RAS_PS": "ACTIVE até PRECHARGE.",
    "T_RC_PS": "ACTIVE até ACTIVE no mesmo banco.",
    "T_RFC_PS": "AUTO REFRESH até qualquer comando.",
    "T_WR_PS": "Último dado de escrita até PRECHARGE.",
    "T_MRD_CK": "LOAD MODE REGISTER até qualquer comando, em clocks.",
    "T_INIT_PS": "Espera com clock estável antes do primeiro comando.",
    "T_REFI_PS": "Intervalo entre refreshes.",
    "INIT_REFRESHES": "Comandos AUTO REFRESH da sequência de energização.",
}
_ORGANIZATION = {
    "row_bits": "ROW_BITS",
    "col_bits": "COL_BITS",
    "width": "DQ_WIDTH",
}


@dataclass(frozen=True)
class IoDelays:
    """Atrasos de E/S de um chip contra o relógio que sai pelo pino.

    Attributes
    ----------
    output_max_ns : float
        Atraso máximo de saída (setup de entrada do chip).
    output_min_ns : float
        Atraso mínimo de saída (menos o hold de entrada do chip).
    input_max_ns : float
        Atraso máximo de entrada (tempo de acesso).
    input_min_ns : float
        Atraso mínimo de entrada (hold de saída do chip).
    """

    output_max_ns: float
    output_min_ns: float
    input_max_ns: float
    input_min_ns: float


def package_name(chip: str) -> str:
    """Dá o nome do pacote VHDL de um chip.

    Parameters
    ----------
    chip : str
        Nome do chip no catálogo.

    Returns
    -------
    str
        `chip_<nome>_pkg`, em minúsculas e com `_` no lugar dos
        caracteres que o VHDL não aceita.
    """
    return (
        "chip_" + re.sub(r"[^a-z0-9]+", "_", chip.lower()).strip("_") + "_pkg"
    )


def chip_io_delays(chip: dict[str, Any]) -> IoDelays:
    """Lê os atrasos de E/S de um chip.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip, com `io_timing`.

    Returns
    -------
    IoDelays
        Os quatro atrasos do `.sdc`.

    Raises
    ------
    InputError
        Se o chip não declara algum campo de `io_timing`.
    """
    timing = cast(dict[str, Any], chip.get("io_timing") or {})
    try:
        return IoDelays(
            output_max_ns=float(timing["input_setup_ns"]),
            output_min_ns=-float(timing["input_hold_ns"]),
            input_max_ns=float(timing["access_ns"]),
            input_min_ns=float(timing["output_hold_ns"]),
        )
    except KeyError as error:
        raise InputError(
            f"chip {chip.get('chip')}: io_timing without {error}"
        ) from error


def _constant_name(key: str) -> str:
    """Dá o nome da constante VHDL de uma chave de tempo.

    Parameters
    ----------
    key : str
        Chave do catálogo (`trcd_ps`, `init_refreshes`).

    Returns
    -------
    str
        `T_RCD_PS` para as chaves `t<nome>_<unidade>`, ou a chave em
        maiúsculas.
    """
    if re.fullmatch(r"t[a-z0-9]+_(ps|ns|ck)", key):
        return "T_" + key[1:].upper()
    return key.upper()


def _number(value: int) -> str:
    """Escreve um inteiro com separador de milhar quando é grande.

    Parameters
    ----------
    value : int
        O valor.

    Returns
    -------
    str
        O literal VHDL.
    """
    return f"{value:_}" if value >= _GROUP_FROM else str(value)


def _require_sdram_timing(
    chip: dict[str, Any], timing: dict[str, Any]
) -> None:
    """Exige todos os tempos de uma SDRAM.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip.
    timing : dict of {str: Any}
        Os tempos do chip.

    Raises
    ------
    InputError
        Se falta um tempo obrigatório.
    """
    missing = [k for k in _SDRAM_REQUIRED if k not in timing]
    if missing:
        raise InputError(f"chip {chip['chip']}: timing without {missing}")


def _constants(chip: dict[str, Any], burst: int) -> list[tuple[str, str, str]]:
    """Lista as constantes do pacote.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip.
    burst : int
        Comprimento da rajada da SDRAM, 1 ou 2 (ou outro suportado).

    Returns
    -------
    list of tuple of (str, str, str)
        Nome, tipo e valor VHDL de cada constante, com o comentário na
        quarta posição concatenada ao nome por `|`.

    Raises
    ------
    InputError
        Se a SDRAM não tem um tempo obrigatório.
    """
    timing = cast(dict[str, Any], chip.get("timing") or {})
    kind = chip.get("kind")
    if kind == "sdram":
        _require_sdram_timing(chip, timing)
    out: list[tuple[str, str, str]] = [
        (
            f"{_constant_name(str(key))}|"
            + _COMMENTS.get(
                _constant_name(str(key)), f"Tempo {key} do catálogo do chip."
            ),
            "natural",
            _number(math.ceil(float(value))),
        )
        for key, value in timing.items()
    ]
    organization = cast(dict[str, Any], chip.get("organization") or {})
    out.extend(
        (
            f"{name}|Parâmetro {key} da organização do chip.",
            "natural",
            str(organization[key]),
        )
        for key, name in _ORGANIZATION.items()
        if key in organization
    )
    out.extend(
        (
            f"{key.upper()}|Tamanho em bytes do {key}.",
            "natural",
            str(chip[key]),
        )
        for key in ("sector_bytes", "boot_sector_bytes")
        if key in chip
    )
    if kind in ("nor", "sram") and {"words", "width"} <= organization.keys():
        size = int(organization["words"]) * int(organization["width"]) // 8
        out.append(
            ("SIZE_BYTES|Tamanho do chip em bytes.", "natural", str(size))
        )
    if kind == "sdram":
        out += _sdram_mode(chip, organization, burst)
    return out


def _sdram_mode(
    chip: dict[str, Any], organization: dict[str, Any], burst: int
) -> list[tuple[str, str, str]]:
    """Lista as constantes de modo de uma SDRAM.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip.
    organization : dict of {str: Any}
        A organização do chip.
    burst : int
        Comprimento da rajada.

    Returns
    -------
    list of tuple of (str, str, str)
        Latência CAS, bits de banco e registrador de modo.

    Raises
    ------
    InputError
        Se a latência CAS ou a rajada não cabem no registrador.
    """
    cas = int(chip.get("cas_latency", 0))
    if not 1 <= cas <= _MODE_WIDTH or burst not in (1, 2, 4, 8):
        raise InputError(
            f"chip {chip['chip']}: cas_latency {cas} or burst {burst} "
            "outside the mode register"
        )
    # A0..A2 comprimento da rajada, A3 sequencial, A4..A6 latência CAS.
    mode = (burst.bit_length() - 1) | (cas << 4)
    bank_bits = int(organization.get("banks", 4)).bit_length() - 1
    return [
        ("CAS_LATENCY|Latência CAS em clocks.", "natural", str(cas)),
        (
            "BANK_BITS|Bits de endereço de banco.",
            "natural",
            str(bank_bits),
        ),
        (
            "MODE_REG|Registrador de modo: rajada sequencial com a "
            f"latência CAS do chip e rajada de {burst}.",
            "std_logic_vector(12 downto 0)",
            f'"{mode:013b}"',
        ),
    ]


def render_chip_package(chip: dict[str, Any], burst: int = 2) -> str:
    """Escreve o pacote VHDL de um chip.

    Parameters
    ----------
    chip : dict of {str: Any}
        O chip do catálogo, com `extends` resolvido.
    burst : int, optional
        Comprimento da rajada da SDRAM, `32 / largura do barramento`;
        2 para um barramento de 16 bits.

    Returns
    -------
    str
        O texto do arquivo `chip_<chip>_pkg.vhd`.
    """
    name = package_name(str(chip["chip"]))
    lines = [
        "-- " + "=" * 77,
        f"-- Tempos do chip {chip['chip']} (arquivo gerado, não edite)",
        "--",
        "-- Gerado pelo riscv-tools a partir do catálogo de chips; os mesmos",
        "-- números alimentam o controlador, o modelo do chip e o .sdc.",
        "-- " + "=" * 77,
        "",
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "",
        f"package {name} is",
        "",
    ]
    for label, vtype, value in _constants(chip, burst):
        const, note = label.split("|", 1)
        lines += [
            f"  -- {note}",
            f"  constant {const} : {vtype} := {value};",
        ]
    lines += ["", f"end package {name};", ""]
    return "\n".join(lines)
