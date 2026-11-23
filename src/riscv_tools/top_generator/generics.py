"""Escreve os generics do SoC no topo da placa."""

from typing import Any, cast

from riscv_tools.board_clocks import ClockPlan
from riscv_tools.board_ports import Port
from riscv_tools.memory_map.timers import has_timer
from riscv_tools.top_generator.spec import (
    TopSpec,
    console,
    external,
    flash_ctrl_index,
    peripheral_index,
    role_ports,
)

_NO_INTERRUPTS = {
    "clint_tick_cycles": "1",
    "plic_n_sources": "6",
    "plic_priority_bits": "3",
    "plic_addr_width": "20",
}
# O SoC exige `plic_n_sources` de 6 a 1023, e o pacote do mapa traz o
# maior identificador de fonte, que numa plataforma com poucas linhas é
# menor que 6; o `max_of` do pacote do interconector aplica o piso (o
# Quartus Lite não tem a função `maximum`).
_PLIC_FROM_PACKAGE = {
    "clint_tick_cycles": "CLINT_TICK_CYCLES",
    "plic_n_sources": "work.interconnect_pkg.max_of(6, (0 => PLIC_N_SOURCES))",
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
        "rom_end_kib => FLASH_END_KIB",
        "ram_base_kib => RAM_BASE_KIB",
        "ram_end_kib => RAM_END_KIB",
        f"rom_external => {str('rom' in regions).lower()}",
        f"ram_external => {str('ram' in regions).lower()}",
        "has_icache => HAS_ICACHE",
        "icache_size_bits => ICACHE_SIZE_BITS",
        "dcache_size_bits => DCACHE_SIZE_BITS",
        "cache_window_bits => I_CACHE_WINDOW_BITS",
        *_interrupt_generics(spec),
        *_table_generics(),
        *_index_generics(spec, (("clint", "CLINT"), ("plic", "PLIC"))),
        *timer_generics(spec),
    ]
    generics += dcache_generics(spec)
    if "zihpm" in str(spec.platform.get("profile", "")).lower():
        generics += ["hpm_counters => HPM_COUNTERS", "hpm_width => HPM_WIDTH"]
    return generics + _timing_generics(spec) + _role_generics(spec)


def dcache_generics(spec: TopSpec) -> list[str]:
    """Monta os generics da fila, da memória interna e da leitura cedo.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic; vazia sem fila, memória interna ou
        leitura adiantada.
    """
    memory = cast(dict[str, Any], spec.platform.get("memory") or {})
    entry = memory.get("dcache")
    dcache = cast(dict[str, Any], entry) if isinstance(entry, dict) else {}
    generics: list[str] = []
    depth = int(dcache.get("write_buffer", 0))
    if depth:
        generics.append(f"dcache_write_buffer => {depth}")
    kib = int(dcache.get("scratch_kib", 0))
    if kib:
        base = int(dcache.get("scratch_base", 0)) // 1024
        generics += [
            f"dcache_scratch_kib => {kib}",
            f"dcache_scratch_base_kib => {base}",
        ]
    if dcache.get("early_lookup") is True:
        generics.append("dcache_early_lookup => true")
    if dcache.get("valid_in_ram") is True:
        generics.append("dcache_valid_in_ram => true")
    return generics


def timer_generics(spec: TopSpec) -> list[str]:
    """Monta os generics dos temporizadores de uso geral.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As tabelas `TIMER_INDICES` e `TIMER_IRQ_IDS` do pacote do mapa,
        uma instância do temporizador por linha delas; nada quando a
        plataforma não tem temporizador.
    """
    if not has_timer(spec.platform):
        return []
    return [
        "timer_indices => TIMER_INDICES",
        "timer_irq_ids => TIMER_IRQ_IDS",
    ]


def fetch_aligned(plan: ClockPlan) -> bool:
    """Diz se o relógio de busca é o do núcleo (mesma freq. e fase).

    Parameters
    ----------
    plan : ClockPlan
        Os relógios da geração.

    Returns
    -------
    bool
        Verdadeiro quando existe `fetch` com a frequência e a fase de
        `core`: as memórias de instrução leem, na borda do núcleo, o
        endereço do PC do ciclo seguinte (`early_fetch_addr`), e o laço
        do PC até a cache de instruções não depende de fase.
    """
    fetch = plan.get("fetch")
    core = plan.get("core")
    return (
        fetch is not None
        and core is not None
        and fetch.mhz == core.mhz
        and fetch.phase_ps == core.phase_ps
    )


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
        instruções (com o relógio de busca defasado do núcleo, ou com o
        endereço do PC do ciclo seguinte quando o de busca tem a fase do
        núcleo), página
        da RAM fora da cache de dados, falhas de acesso com as janelas
        válidas do mapa e controlador de FLASH.
    """
    staggered = spec.plan.get("fetch") is not None
    aligned = fetch_aligned(spec.plan)
    out = [
        "registered_irqs => true",
        "strict_periph => STRICT_PERIPH",
    ]
    if staggered:
        out.append("fast_icache_select => true")
    if aligned:
        out.append("early_fetch_addr => true")
    if "ram" in external(spec):
        out += ["has_dcache_bypass => true", "bypass_page => RAM_LAST_PAGE"]
    ctrl = flash_ctrl_index(spec)
    if ctrl is not None:
        out += [
            "has_flash_ctrl => true",
            "flash_ctrl_index => FLASH_CTRL_INDEX",
        ]
    return out


def _table_generics() -> list[str]:
    """Monta os generics com as tabelas de janelas do pacote do mapa.

    Returns
    -------
    list of str
        A quantidade de periféricos e as tabelas de bases e de máscaras,
        que o interconector usa para decodificar cada periférico; as
        tabelas passam por conversão porque o pacote do mapa declara o
        próprio tipo de vetor de endereços, e o SoC espera outro.
    """
    cast_to = "work.interconnect_pkg.addr_array_t"
    return [
        "periph_count => PERIPH_COUNT",
        f"periph_bases => {cast_to}(PERIPH_BASES)",
        f"periph_masks => {cast_to}(PERIPH_MASKS)",
    ]


def _index_generics(
    spec: TopSpec, names: tuple[tuple[str, str], ...]
) -> list[str]:
    """Monta os generics de índice dos periféricos da plataforma.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    names : tuple of tuple of (str, str)
        O prefixo do generic e o nome do periférico em `peripherals`.

    Returns
    -------
    list of str
        `<prefixo>_index => <NOME>_INDEX` de cada periférico listado; o
        índice vem do pacote do mapa, nunca de um número fixo no topo.
    """
    return [
        f"{prefix}_index => {name}_INDEX"
        for prefix, name in names
        if peripheral_index(spec.platform, name) is not None
    ]


def _mapped_ports(spec: TopSpec, role: str) -> list[Port]:
    """Filtra as portas de um papel que a plataforma mapeia.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    role : str
        O papel, que é também o nome do periférico em minúsculas.

    Returns
    -------
    list of Port
        As portas do papel; vazia quando o `platform.yaml` não lista o
        periférico, pois sem janela o SoC rejeita o índice.
    """
    if peripheral_index(spec.platform, role.upper()) is None:
        return []
    return role_ports(spec, role)


def _role_generics(spec: TopSpec) -> list[str]:
    """Monta os generics dos papéis de E/S e do console.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic, com largura e polaridade por papel;
        chaves e botões só são ligados quando o `platform.yaml` os
        mapeia como periférico, pois sem janela o SoC rejeita o índice.
    """
    out: list[str] = []
    for role in ("switches", "keys"):
        ports = _mapped_ports(spec, role)
        out.append(f"has_{role} => {str(bool(ports)).lower()}")
        if ports:
            out += [
                f"{role}_width => {ports[0].width}",
                f"{role}_active_low => "
                f"{str(ports[0].active == 'low').lower()}",
            ]
    digits = role_ports(spec, "display")
    out += [
        f"has_display => {str(bool(digits)).lower()}",
    ]
    if digits:
        out += [
            f"display_digits => {len(digits)}",
            f"display_active_low => {str(digits[0].active == 'low').lower()}",
        ]
    jtag = console(spec) == "jtag"
    out += [
        f"has_uart_jtag => {str(jtag).lower()}",
        f"has_uart_pins => {str(not jtag).lower()}",
    ]
    return out + _index_generics(
        spec,
        (
            ("switches", "SWITCHES"),
            ("keys", "KEYS"),
            ("display", "DISPLAY"),
            ("uart_jtag", "UART"),
            ("uart_pins", "UART"),
        ),
    )


def video_generics(spec: TopSpec) -> list[str]:
    """Escreve os generics do vídeo resolvido.

    Os generics ficam disponíveis para a instância do periférico de
    vídeo; o topo ainda não a instancia, de modo que o mapa de generics
    do SoC não os recebe.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic; vazia quando a plataforma não pede
        vídeo.
    """
    return [] if spec.video is None else spec.video.generics()
