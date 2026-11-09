"""Escreve os generics do SoC no topo da placa."""

from typing import Any, cast

from riscv_tools.top_generator.spec import (
    TopSpec,
    console,
    external,
    flash_ctrl_id,
    role_ports,
)

_NO_INTERRUPTS = {
    "clint_tick_cycles": "1",
    "plic_n_sources": "6",
    "plic_priority_bits": "3",
    "plic_addr_width": "20",
}
_PLIC_FROM_PACKAGE = {
    "clint_tick_cycles": "CLINT_TICK_CYCLES",
    "plic_n_sources": "PLIC_N_SOURCES",
    "plic_priority_bits": "PLIC_PRIORITY_BITS",
    "plic_addr_width": "PLIC_ADDR_WIDTH",
}


def _interrupt_generics(spec: TopSpec) -> list[str]:
    """Escreve os generics de interrupção do SoC.

    Os valores vêm do pacote do mapa quando a plataforma tem PLIC e são
    os padrões do SoC caso contrário, de modo que as constantes
    `PLIC_*` e `CLINT_*` nunca são lidas de um pacote que não as tem.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic.
    """
    section = cast(dict[str, Any], spec.platform.get("interrupts") or {})
    wired = "sources" in section or "plic" in section
    values = _PLIC_FROM_PACKAGE if wired else _NO_INTERRUPTS
    return [f"{name} => {value}" for name, value in values.items()]


def soc_generics(spec: TopSpec) -> list[str]:
    """Monta os generics do SoC.

    As extensões de ISA não são generics do SoC; ele as lê do
    `config_pkg` da plataforma.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic.
    """
    regions = external(spec)
    generics = [
        "boot_memory_size_bytes => BOOT_MEMORY_SIZE_BYTES",
        "rom_end_kib => ROM_END_KIB",
        "ram_base_kib => RAM_BASE_KIB",
        "ram_end_kib => RAM_END_KIB",
        "ext_base_kib => EXT_BASE_KIB",
        "periph_base_kib => PERIPH_BASE_KIB",
        f"rom_external => {str('rom' in regions).lower()}",
        f"ram_external => {str('ram' in regions).lower()}",
        "has_icache => HAS_ICACHE",
        "icache_size_bits => ICACHE_SIZE_BITS",
        "dcache_size_bits => DCACHE_SIZE_BITS",
        "cache_window_bits => CACHE_WINDOW_BITS",
        *_interrupt_generics(spec),
        f"clint_id => {_peripheral_id(spec.platform, 'CLINT', 6)}",
        f"plic_id => {_peripheral_id(spec.platform, 'PLIC', 7)}",
    ]
    if "zihpm" in str(spec.platform.get("profile", "")).lower():
        generics += ["hpm_counters => HPM_COUNTERS", "hpm_width => HPM_WIDTH"]
    return generics + _timing_generics(spec) + _role_generics(spec)


def _timing_generics(spec: TopSpec) -> list[str]:
    """Monta os generics do SoC que cortam caminho crítico da placa.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas: interrupções registradas, seleção rápida da cache de
        instruções (com o relógio de busca defasado do núcleo), página
        da RAM fora da cache de dados, falhas de acesso com as janelas
        válidas do mapa e controlador de FLASH.
    """
    staggered = spec.plan.get("fetch") is not None
    out = [
        "registered_irqs => true",
        "periph_slots => PERIPH_SLOTS",
    ]
    if staggered:
        out.append("fast_icache_select => true")
    if "ram" in external(spec):
        out += ["has_dcache_bypass => true", "bypass_page => RAM_LAST_PAGE"]
    ctrl = flash_ctrl_id(spec)
    if ctrl is not None:
        out += ["has_flash_ctrl => true", f"flash_ctrl_id => {ctrl}"]
    return out


def _peripheral_id(platform: dict[str, Any], name: str, default: int) -> int:
    """Lê o índice da janela de um periférico.

    Parameters
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.
    name : str
        O periférico.
    default : int
        O índice quando a plataforma não o lista.

    Returns
    -------
    int
        O `id` do periférico.
    """
    for entry in cast(list[dict[str, Any]], platform.get("peripherals") or []):
        if entry.get("name") == name:
            return int(entry["id"])
    return default


def _role_generics(spec: TopSpec) -> list[str]:
    """Monta os generics dos papéis de E/S e do console.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic, com largura e polaridade por papel.
    """
    out: list[str] = []
    for role, name, default_id in (
        ("switches", "SWITCHES", 1),
        ("keys", "KEYS", 2),
    ):
        ports = role_ports(spec, role)
        out += [
            f"has_{role} => {str(bool(ports)).lower()}",
            f"{role}_id => {_peripheral_id(spec.platform, name, default_id)}",
        ]
        if ports:
            out += [
                f"{role}_width => {ports[0].width}",
                f"{role}_active_low => "
                f"{str(ports[0].active == 'low').lower()}",
            ]
    digits = role_ports(spec, "display")
    out += [
        f"has_display => {str(bool(digits)).lower()}",
        f"display_id => {_peripheral_id(spec.platform, 'DISPLAY', 5)}",
    ]
    if digits:
        out += [
            f"display_digits => {len(digits)}",
            f"display_active_low => {str(digits[0].active == 'low').lower()}",
        ]
    uart_id = _peripheral_id(spec.platform, "UART", 4)
    jtag = console(spec) == "jtag"
    out += [
        f"has_uart_jtag => {str(jtag).lower()}",
        f"uart_jtag_id => {uart_id}",
        f"has_uart_pins => {str(not jtag).lower()}",
        f"uart_pins_id => {uart_id}",
    ]
    return out
