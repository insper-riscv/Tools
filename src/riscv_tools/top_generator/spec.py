"""Descrição do topo da placa e consultas à plataforma dele."""

from dataclasses import dataclass, field
from typing import Any, cast

from riscv_tools.board_clocks import ClockPlan
from riscv_tools.board_ports import Port
from riscv_tools.board_video import VideoPlan


@dataclass(frozen=True)
class TopSpec:
    """O que o topo precisa além das portas.

    Attributes
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.
    plan : ClockPlan
        Os relógios.
    ports : tuple of Port
        As portas do topo.
    pll_module : str
        Nome do módulo do PLL.
    entity : str
        Nome da entidade do topo.
    chip_packages : dict of {str: str}
        Nome do pacote de tempos por tipo de memória.
    video : VideoPlan or None
        O vídeo resolvido; `None` quando a plataforma não pede vídeo.
    """

    platform: dict[str, Any]
    plan: ClockPlan
    ports: tuple[Port, ...]
    pll_module: str
    entity: str
    chip_packages: dict[str, str]
    video: VideoPlan | None = None


@dataclass(frozen=True)
class RenderedTop:
    """O topo escrito e os avisos achados.

    Attributes
    ----------
    text : str
        O arquivo `.vhd`.
    warnings : list of str
        Backends e papéis que o topo não pôde ligar.
    """

    text: str
    warnings: list[str] = field(default_factory=list[str])


def role_ports(spec: TopSpec, role: str) -> list[Port]:
    """Filtra as portas de um papel.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    role : str
        O papel.

    Returns
    -------
    list of Port
        As portas.
    """
    return [p for p in spec.ports if p.role == role]


def external(spec: TopSpec) -> dict[str, tuple[str, str]]:
    """Lista as regiões externas e seus backends.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    dict of {str: tuple of (str, str)}
        Para `rom` e `ram`: o backend e o dispositivo.
    """
    memory = cast(dict[str, Any], spec.platform.get("memory") or {})
    out: dict[str, tuple[str, str]] = {}
    for key in ("rom", "ram"):
        fields = memory.get(key)
        if isinstance(fields, dict):
            f = cast(dict[str, Any], fields)
            if f.get("external"):
                out[key] = (str(f.get("backend")), str(f.get("device", "")))
    return out


def flash_ctrl_id(spec: TopSpec) -> int | None:
    """Dá a janela do controlador de FLASH da atualização de programa.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    int or None
        O `id` do periférico `FLASH_CTRL` quando a FLASH é emulada e a
        plataforma o declara; senão `None`.
    """
    backend, device = external(spec).get("rom", ("", ""))
    if backend != "emulado" and device != "nor":
        return None
    for item in cast(list[Any], spec.platform.get("peripherals") or []):
        fields = cast(dict[str, Any], item)
        if fields.get("name") == "FLASH_CTRL":
            return int(fields["id"])
    return None


def console(spec: TopSpec) -> str:
    """Lê o console da plataforma.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    str
        `jtag` ou `pinos`.
    """
    return str(spec.platform.get("console", "jtag"))
