"""Pede ao PLL os relógios de envio do Ethernet RGMII.

O RGMII a 1000 Mbit/s manda um byte por ciclo de 125 MHz, com o nibble
alto na borda de descida. O envio usa um relógio livre de 125 MHz
(`eth_tx`), e o `GTX_CLK` que sai pelo pino é o mesmo relógio deslocado
de um quarto de ciclo (`eth_tx_dly`), de modo que o PHY amostre os dados
no meio do olho. Com `shifted_txc` em falso o PHY insere o atraso, e o
`GTX_CLK` sai do próprio `eth_tx`.
"""

from fractions import Fraction
from typing import Any

from riscv_tools.memory_map.external import external_list
from riscv_tools.memory_map.kinds import EXTERNAL

# Relógio do envio e do `GTX_CLK` do RGMII, em MHz.
ETH_TX_MHZ = Fraction(125)
# Um quarto do ciclo de 125 MHz, em picossegundos.
ETH_QUARTER_PS = 2000
ETH_TX = "eth_tx"
ETH_TX_DLY = "eth_tx_dly"


def _rgmii(platform: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista os periféricos Ethernet que usam o RGMII."""
    return [
        item
        for item in external_list(platform)
        if item["kind"] == "eth"
        and EXTERNAL["eth"].variant(item) is EXTERNAL["eth"].variants["rgmii"]
    ]


def eth_requests(platform: dict[str, Any]) -> list[tuple[str, Fraction, int]]:
    """Dá os relógios que o RGMII da plataforma pede ao PLL.

    Parameters
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.

    Returns
    -------
    list of tuple of (str, Fraction, int)
        Papel, frequência em MHz e fase em picossegundos. Vazio sem
        RGMII; só `eth_tx` quando todo RGMII atrasa o relógio no PHY;
        senão `eth_tx` e `eth_tx_dly`.
    """
    items = _rgmii(platform)
    if not items:
        return []
    out = [(ETH_TX, ETH_TX_MHZ, 0)]
    if any(bool(item.get("shifted_txc", True)) for item in items):
        out.append((ETH_TX_DLY, ETH_TX_MHZ, ETH_QUARTER_PS))
    return out
