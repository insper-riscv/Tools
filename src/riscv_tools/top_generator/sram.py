"""Escreve o backend de dispositivo da RAM em SRAM assíncrona.

O backend é o `sram_ctrl` do Memory, que atende a porta de dados do SoC
com o contrato do `ram_chip` e comanda os pinos de uma SRAM de 1M x 16
(endereço, `CE#`, `OE#`, `WE#`, `LB#` e `UB#`). Os tempos do chip são os
padrões do `chip_timing_pkg`, e o topo só informa o período do relógio,
a margem de pino e o tamanho do chip.
"""

import math
import re

from riscv_tools.top_generator import backends
from riscv_tools.top_generator.spec import TopSpec, role_ports

# Pino do chip e porta do controlador que o recebe.
SRAM_PIN_MAP = {
    "addr": "o_sram_addr",
    "ce_n": "o_sram_ce_n",
    "oe_n": "o_sram_oe_n",
    "we_n": "o_sram_we_n",
    "lb_n": "o_sram_lb_n",
    "ub_n": "o_sram_ub_n",
}
# Larguras do chip que o controlador atende: endereço de palavra de 16
# bits e dados de 16 bits.
SRAM_ADDR_WIDTH = 20
SRAM_DQ_WIDTH = 16
# Margem somada a cada tempo do chip para o atraso de pino e de placa,
# em ns, a mesma que o backend da FLASH NOR usa.
SRAM_MARGIN_NS = 5
# Tamanho que o controlador assume sem o pacote do chip, em bytes.
SRAM_DEFAULT_BYTES = 2 * 1024 * 1024


def sram_key(name: str) -> str:
    """Classifica uma porta da SRAM pelo sufixo do nome.

    Parameters
    ----------
    name : str
        Nome da porta (`SRAM_CE_N`).

    Returns
    -------
    str
        `addr`, `dq`, `ce_n` e assim por diante.
    """
    return re.sub(r"^sram_?", "", name.lower())


def sram_backend(spec: TopSpec, notes: list[str]) -> tuple[list[str], str]:
    """Escreve o backend de dispositivo da SRAM.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    notes : list of str
        Recebe os avisos.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais e o corpo; vazios, com aviso, quando a placa não tem
        os pinos do chip ou as larguras dele.
    """
    pin_map = {sram_key(p.name): p for p in role_ports(spec, "sram")}
    missing = [
        key for key in (*SRAM_PIN_MAP, "addr", "dq") if key not in pin_map
    ]
    shape = (
        missing
        or pin_map["addr"].width != SRAM_ADDR_WIDTH
        or pin_map["dq"].width != SRAM_DQ_WIDTH
    )
    if shape:
        notes.append(
            f"W sram pins {missing or 'widths'} missing or not "
            f"{SRAM_ADDR_WIDTH} address and {SRAM_DQ_WIDTH} data bits; "
            "no SRAM backend was instantiated"
        )
        return [], ""
    core = spec.plan.get("core")
    chip = spec.chip_packages.get("sram", "")
    fields = {
        "period_ns": math.floor(float(core.period_ns)) if core else 20,
        "margin_ns": SRAM_MARGIN_NS,
        "size": f"work.{chip}.SIZE_BYTES" if chip else SRAM_DEFAULT_BYTES,
        "pins": ",\n".join(
            f"\t\t\t{formal} => {pin_map[key].name}"
            for key, formal in SRAM_PIN_MAP.items()
        ),
        "dq_name": pin_map["dq"].name,
    }
    return (
        backends.template("sram_signals").rstrip().split("\n"),
        backends.template("sram_body").format(**fields),
    )
