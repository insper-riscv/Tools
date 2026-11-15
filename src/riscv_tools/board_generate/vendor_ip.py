"""Acrescenta ao projeto o IP do fabricante que as fontes pedem.

O ADC do MAX 10 usa o núcleo `altera_modular_adc`, um IP do Quartus que
o Platform Designer gera a partir de um script do `Peripherals`
(`ip/generate.sh`). O VHDL só o instancia como `component`, então o
projeto precisa do `.qip` gerado e de um passo que o produza. Este
módulo reconhece o IP pelo arquivo que o instancia entre as fontes e
escreve a linha do `.qsf` e o script que chama o gerador.
"""

import posixpath
from dataclasses import dataclass, field
from typing import Any

from riscv_tools.memory_map.external import external_list

# O arquivo que instancia o núcleo, a pasta do gerador ao lado dele e o
# `.qip` que o gerador escreve sob a pasta de saída.
MAX10_INSTANCE = "max10_adc_ip.vhd"
MAX10_QIP = "max10_adc_core/synthesis/max10_adc_core.qip"
GENERATE_SCRIPT = "generate_ip.sh"


@dataclass(frozen=True)
class VendorIp:
    """O que o IP do fabricante acrescenta ao projeto.

    Attributes
    ----------
    qsf_lines : tuple of str
        Atribuições do `.qsf`.
    files : dict of {str: str}
        Arquivos do projeto, por nome.
    """

    qsf_lines: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict[str, str])


def _script(generator: str) -> str:
    """Escreve o script que gera o IP na pasta do projeto."""
    return (
        "#!/usr/bin/env bash\n"
        "# Gera o IP do ADC do MAX 10 na pasta do projeto (arquivo gerado,\n"
        "# não edite). Rode antes de compilar; exige o Quartus Prime Lite\n"
        "# (QUARTUS_ROOTDIR) e escreve max10_adc_core/synthesis/.\n"
        "set -euo pipefail\n"
        'here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        f'"$here/{generator}" "$here"\n'
    )


def uses_max10(platform: dict[str, Any]) -> bool:
    """Tell whether the platform has the internal ADC of the MAX 10."""
    return any(
        item["kind"] == "adc" and item.get("chip") == "max10"
        for item in external_list(platform)
    )


def vendor_ip(sources: tuple[str, ...], platform: dict[str, Any]) -> VendorIp:
    """Reconhece o IP do fabricante entre as fontes do projeto.

    Parameters
    ----------
    sources : tuple of str
        As fontes, como aparecem no `.qsf` (relativas ao projeto).
    platform : dict of {str: Any}
        O `platform.yaml`; o IP só entra com um `adc` de `chip: max10`.

    Returns
    -------
    VendorIp
        A linha `QIP_FILE` e o script `generate_ip.sh` quando as fontes
        trazem o arquivo que instancia o núcleo e a plataforma usa o ADC
        do MAX 10; vazio senão.
    """
    if not uses_max10(platform):
        return VendorIp()
    for path in sources:
        if posixpath.basename(path) == MAX10_INSTANCE:
            folder = posixpath.dirname(path)
            generator = posixpath.join(folder, "ip", "generate.sh")
            return VendorIp(
                (f"set_global_assignment -name QIP_FILE {MAX10_QIP}",),
                {GENERATE_SCRIPT: _script(generator)},
            )
    return VendorIp()
