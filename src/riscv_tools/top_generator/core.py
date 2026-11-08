"""Escreve o topo da placa: só liga PLL, SoC, backends e pinos.

O topo instancia a entidade `soc` do Insper-RISC-V, com os generics
lidos do pacote do mapa da plataforma (o pacote que o
`generate-memory-map` escreve), e um backend por região externa, feito
das entidades do Memory (ver `backends`). Os nomes e as portas são os
reais dessas entidades.

Ligação dos papéis ao SoC.

- `switches` e `keys`: pinos de GPIO, portas `inout` ligadas direto a
  `io_switches` e `io_keys`, com a polaridade no generic `*_active_low`.
- `display`: `o_display_hex` fatiado em uma porta de 7 bits por dígito,
  na polaridade `display_active_low`, e nó `virtual_jtag` de índice 2
  nas portas `i_display_*`, pelo qual o hospedeiro grava o registrador.
- `leds`: o SoC não exporta LEDs; os pinos ficam no nível apagado, menos
  o primeiro, que acende com a bandeira de falha do display.
- console `jtag`: nó `virtual_jtag` de índice 1 nas portas `i_uart_*`.
- console `pinos`: portas `rx` e `tx` da placa em `i_uart_rx` e
  `o_uart_tx`.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, cast

from riscv_tools.board_clocks import PLL_INSTANCE, ClockPlan
from riscv_tools.board_ports import Port
from riscv_tools.top_generator import backends

SOC_ENTITY = "soc"
# Índice do nó Virtual JTAG da UART; o 0 é o carregador da FLASH e o 3
# a depuração da SDRAM.
UART_JTAG_INSTANCE = 1
# Índice do nó Virtual JTAG do display, pelo qual o hospedeiro lê e
# escreve o registrador e a bandeira de falha.
DISPLAY_JTAG_INSTANCE = 2
_SDRAM_ACTIVE_LOW = ("cas", "ras", "we", "cs")
# Valores do SoC sem interrupções, que o pacote do mapa não traz.
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
_EXTENSIONS = (
    "has_zicsr",
    "has_zicntr",
    "has_zihpm",
    "has_zimop",
    "has_zicond",
    "has_zihintntl",
    "has_zihintpause",
    "has_m",
    "has_zmmul",
    "has_zifencei",
    "has_zicclsm",
    "has_interrupts",
    "has_sscofpmf",
    "has_e",
)


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
    """

    platform: dict[str, Any]
    plan: ClockPlan
    ports: tuple[Port, ...]
    pll_module: str
    entity: str
    chip_packages: dict[str, str]


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
    warnings: list[str] = field(default_factory=lambda: [])


def top_name(platform: str, board: str) -> str:
    """Dá o nome da entidade do topo.

    Parameters
    ----------
    platform : str
        Nome da plataforma.
    board : str
        Nome da placa.

    Returns
    -------
    str
        `<plataforma>_<placa>_top` com `_` no lugar de `-`.
    """
    return re.sub(r"[^a-z0-9]+", "_", f"{platform}_{board}_top".lower())


def _vtype(width: int, vector: bool) -> str:
    """Escreve o tipo VHDL de um sinal.

    Parameters
    ----------
    width : int
        Largura em bits.
    vector : bool
        Se é vetor.

    Returns
    -------
    str
        `std_logic` ou `std_logic_vector(w-1 downto 0)`.
    """
    if not vector:
        return "std_logic"
    return f"std_logic_vector({width - 1} downto 0)"


def _role(spec: TopSpec, role: str) -> list[Port]:
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


def _package(platform: dict[str, Any]) -> str:
    """Lê o nome do pacote do mapa da plataforma.

    Parameters
    ----------
    platform : dict of {str: Any}
        O `platform.yaml`.

    Returns
    -------
    str
        `generate.vhdl.package`.

    Raises
    ------
    ValueError
        Se a plataforma não declara o pacote.
    """
    generate = cast(dict[str, Any], platform.get("generate") or {})
    vhdl = cast(dict[str, Any], generate.get("vhdl") or {})
    if "package" not in vhdl:
        raise ValueError("platform: generate.vhdl.package is required")
    return str(vhdl["package"])


def _external(spec: TopSpec) -> dict[str, tuple[str, str]]:
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


def _flash_ctrl_id(spec: TopSpec) -> int | None:
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
    backend, device = _external(spec).get("rom", ("", ""))
    if backend != "emulado" and device != "nor":
        return None
    for item in cast(list[Any], spec.platform.get("peripherals") or []):
        fields = cast(dict[str, Any], item)
        if fields.get("name") == "FLASH_CTRL":
            return int(fields["id"])
    return None


def _entity(spec: TopSpec) -> list[str]:
    """Escreve a entidade.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    profile = str(spec.platform.get("profile", "")).lower()
    lines = [f"entity {spec.entity} is"]
    if "zihpm" in profile:
        lines += [
            "\tgeneric (",
            "\t\t-- Quantidade de contadores de eventos do Zihpm (de 0 a 29).",
            "\t\tHPM_COUNTERS : natural range 0 to 29 := 29;",
            "\t\t-- Largura, em bits, de cada contador de eventos do Zihpm.",
            "\t\tHPM_WIDTH    : natural range 0 to 64 := 64",
            "\t);",
        ]
    lines.append("\tport (")
    body: list[str] = []
    for port in (p for p in spec.ports if not p.alias):
        # Chaves e botões são pinos de GPIO: o SoC os liga como inout.
        gpio = port.role in ("switches", "keys")
        mode = {"in": "in   ", "out": "out  ", "inout": "inout"}[
            "inout" if gpio else port.direction
        ]
        body.append(
            f"\t\t-- Porta {port.role} da placa.\n"
            f"\t\t{port.name} : {mode} {_vtype(port.width, port.vector)}"
        )
    return [*lines, ";\n".join(body), "\t);", "end entity;", ""]


def _declarations(spec: TopSpec) -> list[str]:
    """Escreve os sinais comuns da arquitetura.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    outs = "".join(
        f"\t\t\toutclk_{i} : out std_logic;\n"
        for i in range(len(spec.plan.roles))
    )
    lines = [
        "\t-- O PLL é um módulo Verilog, instanciado por componente.",
        f"\tcomponent {spec.pll_module} is",
        "\t\tport (",
        "\t\t\trefclk : in std_logic;",
        "\t\t\trst    : in std_logic;",
        outs + "\t\t\tlocked : out std_logic",
        "\t\t);",
        "\tend component;",
        "",
        "\t-- Relógios por papel (K7) e travamento do PLL.",
        "\tsignal clk_core, clk_fetch, clk_mem, clk_mem_pin : std_logic;",
        "\tsignal pll_locked : std_logic;",
        "\t-- Reset do usuário ativo em '1' e reset do SoC.",
        "\tsignal reset_active, rst_async, soc_rst : std_logic;",
        '\tsignal rst_sr : std_logic_vector(1 downto 0) := "11";',
        "\t-- Faces do SoC.",
        "\tsignal if_addr : std_logic_vector(29 downto 0);",
        "\tsignal if_rden : std_logic;",
        "\tsignal boot_data : std_logic_vector(31 downto 0);",
    ]
    digits = _role(spec, "display")
    if digits:
        lines += [
            f"\tsignal display_hex : {_vtype(7 * len(digits), True)};",
            "\tsignal display_tck, display_tdi, display_tdo : std_logic;",
            "\tsignal display_ir_in : std_logic_vector(1 downto 0);",
            "\tsignal display_cdr, display_sdr, display_udr, display_uir"
            " : std_logic;",
            "\tsignal display_fail : std_logic;",
        ]
    if _role(spec, "uart") == [] and _console(spec) == "jtag":
        lines += [
            "\tsignal uart_tck, uart_tdi, uart_tdo : std_logic;",
            "\tsignal uart_ir_in : std_logic_vector(1 downto 0);",
            "\tsignal uart_cdr, uart_sdr, uart_udr, uart_uir : std_logic;",
        ]
    return lines


def _console(spec: TopSpec) -> str:
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


def _pll_and_reset(spec: TopSpec, has_halt: bool) -> list[str]:
    """Escreve a instância do PLL e a lógica de reset.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    has_halt : bool
        Se o carregador da FLASH segura o núcleo em reset.

    Returns
    -------
    list of str
        As linhas.
    """
    reset = _role(spec, "reset")[0]
    reference = _role(spec, "clock")[0]
    source = reset.alias or reset.name
    expr = "not " + source if reset.active == "low" else source
    maps = [f"refclk => {reference.name}", "rst => reset_active"]
    maps += [
        f"outclk_{i} => clk_{c.role}" for i, c in enumerate(spec.plan.roles)
    ]
    maps.append("locked => pll_locked")
    aliases = [
        f"\tclk_{role} <= clk_core;"
        for role in ("fetch", "mem")
        if spec.plan.get(role) is None
    ]
    halt = " or flash_halt" if has_halt else ""
    return [
        f"\treset_active <= {expr};",
        *aliases,
        f"\t{PLL_INSTANCE} : {spec.pll_module}",
        "\t\tport map (" + ", ".join(maps) + ");",
        "",
        "\t-- O SoC sai do reset dois ciclos de core depois do PLL travar.",
        "\trst_async <= (not pll_locked) or reset_active;",
        "\tprocess (clk_core, rst_async)",
        "\tbegin",
        "\t\tif rst_async = '1' then",
        '\t\t\trst_sr <= "11";',
        "\t\telsif rising_edge(clk_core) then",
        "\t\t\trst_sr <= rst_sr(0) & '0';",
        "\t\tend if;",
        "\tend process;",
        f"\tsoc_rst <= rst_sr(1){halt};",
        "",
    ]


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


def _soc_generics(spec: TopSpec) -> list[str]:
    """Monta os generics do SoC.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de generic.
    """
    external = _external(spec)
    generics = [
        "boot_memory_size_bytes => BOOT_MEMORY_SIZE_BYTES",
        "rom_end_kib => ROM_END_KIB",
        "ram_base_kib => RAM_BASE_KIB",
        "ram_end_kib => RAM_END_KIB",
        "ext_base_kib => EXT_BASE_KIB",
        "periph_base_kib => PERIPH_BASE_KIB",
        f"rom_external => {str('rom' in external).lower()}",
        f"ram_external => {str('ram' in external).lower()}",
        "has_icache => HAS_ICACHE",
        "has_dcache => HAS_DCACHE",
        "icache_size_bits => ICACHE_SIZE_BITS",
        "dcache_size_bits => DCACHE_SIZE_BITS",
        "cache_window_bits => CACHE_WINDOW_BITS",
        *(f"{name} => {name.upper()}" for name in _EXTENSIONS),
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
        "has_access_faults => HAS_ACCESS_FAULTS",
        "periph_slots => PERIPH_SLOTS",
    ]
    if staggered:
        out.append("fast_icache_select => true")
    if "ram" in _external(spec):
        out += ["has_dcache_bypass => true", "bypass_page => RAM_LAST_PAGE"]
    ctrl = _flash_ctrl_id(spec)
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
        ports = _role(spec, role)
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
    digits = _role(spec, "display")
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
    jtag = _console(spec) == "jtag"
    out += [
        f"has_uart_jtag => {str(jtag).lower()}",
        f"uart_jtag_id => {uart_id}",
        f"has_uart_pins => {str(not jtag).lower()}",
        f"uart_pins_id => {uart_id}",
    ]
    return out


def _soc_ports(spec: TopSpec) -> list[str]:
    """Monta as portas do SoC.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de porta.
    """
    external = _external(spec)
    maps = [
        "i_clk_core => clk_core",
        "i_clk_fetch => clk_fetch",
        "i_rst => soc_rst",
        "o_if_addr => if_addr",
        "o_if_rden => if_rden",
        "i_boot_data => boot_data",
    ]
    if "rom" in external:
        # Com a FLASH NOR o prefixo é `fx_`, porque `FL_ADDR` e `FL_DQ`
        # são portas da placa e o VHDL não distingue maiúsculas.
        fl = "fx" if external["rom"][1] == "nor" else "fl"
        maps += [
            f"o_flash_addr => {fl}_addr",
            f"o_flash_rden => {fl}_rden",
            f"o_flash_line => {fl}_line",
            f"o_flash_advance => {fl}_adv",
            f"i_flash_ready => {fl}_ready",
            f"i_flash_busy => {fl}_busy",
            f"i_flash_rdata => {fl}_rdata",
            f"i_flash_rdata_x => {fl}_rdx",
        ]
        if _flash_ctrl_id(spec) is not None:
            maps += [
                "o_flash_cmd_valid => fcmd_valid",
                "o_flash_cmd_op => fcmd_op",
                "o_flash_cmd_addr => fcmd_addr",
                "i_flash_cmd_busy => fcmd_busy",
                "i_flash_cmd_wel => fcmd_wel",
                "i_flash_cmd_refused => fcmd_refused",
                "i_flash_buf_idx => fcmd_buf_idx",
                "o_flash_buf_data => fcmd_buf_data",
                "i_inval_valid => fcmd_inval_valid",
                "i_inval_first => fcmd_inval_first",
                "i_inval_last => fcmd_inval_last",
            ]
    if "ram" in external:
        maps += [
            "o_ramd_addr => rd_addr",
            "o_ramd_wdata => rd_wdata",
            "o_ramd_byteena => rd_be",
            "o_ramd_rden => rd_rden",
            "o_ramd_wren => rd_wren",
            "o_ramd_line => rd_line",
            "o_ramd_advance => rd_adv",
            "o_ramd_wdata_x => rd_wdx",
            "i_ramd_ready => rd_ready",
            "i_ramd_rdata => rd_rdata",
            "i_ramd_rdata_x => rd_rdx",
            "o_rami_addr => ri_addr",
            "o_rami_rden => ri_rden",
            "o_rami_line => ri_line",
            "o_rami_advance => ri_adv",
            "i_rami_ready => ri_ready",
            "i_rami_rdata => ri_rdata",
            "i_rami_rdata_x => ri_rdx",
        ]
    return maps + _role_ports(spec)


def _role_ports(spec: TopSpec) -> list[str]:
    """Monta as portas do SoC dos papéis de E/S e do console.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As associações de porta.
    """
    maps = [
        f"io_{port.role} => {port.name}"
        for port in _role(spec, "switches") + _role(spec, "keys")
    ]
    if _role(spec, "display"):
        maps += [
            "o_display_hex => display_hex",
            "i_display_tck => display_tck",
            "i_display_tdi => display_tdi",
            "o_display_tdo => display_tdo",
            "i_display_ir_in => display_ir_in",
            "i_display_state_cdr => display_cdr",
            "i_display_state_sdr => display_sdr",
            "i_display_state_udr => display_udr",
            "i_display_state_uir => display_uir",
            "o_display_fail => display_fail",
        ]
    if _console(spec) == "jtag":
        maps += [
            "i_uart_tck => uart_tck",
            "i_uart_tdi => uart_tdi",
            "o_uart_tdo => uart_tdo",
            "i_uart_ir_in => uart_ir_in",
            "i_uart_state_cdr => uart_cdr",
            "i_uart_state_sdr => uart_sdr",
            "i_uart_state_udr => uart_udr",
            "i_uart_state_uir => uart_uir",
        ]
    else:
        uart = _role(spec, "uart")
        maps += [
            f"i_uart_rx => {uart[0].name}",
            f"o_uart_tx => {uart[1].name}",
        ]
    return maps


def _soc_instance(spec: TopSpec) -> list[str]:
    """Escreve a instância do SoC.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    generics = ",\n".join(f"\t\t\t{g}" for g in _soc_generics(spec))
    ports = ",\n".join(f"\t\t\t{m}" for m in _soc_ports(spec))
    return [
        f"\tsoc_inst : entity work.{SOC_ENTITY}",
        f"\t\tgeneric map (\n{generics}\n\t\t)",
        f"\t\tport map (\n{ports}\n\t\t);",
        "",
    ]


def _io_wiring(spec: TopSpec) -> list[str]:
    """Liga os pinos dos papéis de E/S e do console aos sinais do SoC.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    lines: list[str] = []
    for i, port in enumerate(_role(spec, "display")):
        lines.append(
            f"\t{port.name} <= display_hex({7 * i + 6} downto {7 * i});"
        )
    has_display = bool(_role(spec, "display"))
    for port in _role(spec, "leds"):
        off = "'1'" if port.active == "low" else "'0'"
        fail = "not display_fail" if port.active == "low" else "display_fail"
        if has_display:
            lines.append(f"\t{port.name} <= (0 => {fail}, others => {off});")
        else:
            lines.append(f"\t{port.name} <= (others => {off});")
    if has_display:
        lines += [
            "",
            "\t-- Display pela JTAG: nó Virtual JTAG do registrador.",
            "\tdisplay_vjtag : entity work.virtual_jtag",
            f"\t\tgeneric map (instance_index => {DISPLAY_JTAG_INSTANCE}, "
            'auto_instance_index => "NO", ir_width => 2)',
            "\t\tport map (o_tck => display_tck, o_tdi => display_tdi, "
            "i_tdo => display_tdo, o_ir_in => display_ir_in,",
            "\t\t\to_state_cdr => display_cdr, o_state_sdr => display_sdr, "
            "o_state_udr => display_udr, o_state_uir => display_uir);",
        ]
    if _console(spec) == "jtag":
        lines += [
            "",
            "\t-- Console pela JTAG: nó Virtual JTAG da UART.",
            "\tuart_vjtag : entity work.virtual_jtag",
            f"\t\tgeneric map (instance_index => {UART_JTAG_INSTANCE}, "
            'auto_instance_index => "NO", ir_width => 2)',
            "\t\tport map (o_tck => uart_tck, o_tdi => uart_tdi, "
            "i_tdo => uart_tdo, o_ir_in => uart_ir_in,",
            "\t\t\to_state_cdr => uart_cdr, o_state_sdr => uart_sdr, "
            "o_state_udr => uart_udr, o_state_uir => uart_uir);",
        ]
    return [*lines, ""]


def _sdram_key(name: str) -> str:
    """Classifica uma porta de SDRAM pelo sufixo do nome.

    Parameters
    ----------
    name : str
        Nome da porta (`DRAM_CAS_N`, `oSDRAM_CASn`).

    Returns
    -------
    str
        `addr`, `ba`, `cas_n`, `dq`, `ldqm` e assim por diante.
    """
    key = re.sub(r"^[obi]?s?dram_?", "", name.lower()).replace("_", "")
    for base in _SDRAM_ACTIVE_LOW:
        if key == f"{base}n":
            return f"{base}_n"
    return key


def _sdram_backend(spec: TopSpec, notes: list[str]) -> tuple[list[str], str]:
    """Escreve o backend de SDRAM, se o controlador suporta a placa.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    notes : list of str
        Recebe os avisos.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais e o corpo, vazios quando o controlador de hoje não
        serve (largura de dados diferente de 16 bits).
    """
    pin_map = {_sdram_key(p.name): p for p in _role(spec, "sdram")}
    dq = pin_map["dq"]
    if dq.width not in backends.SDRAM_DQ_WIDTHS:
        notes.append(
            f"W sdram data width {dq.width} is not one of "
            f"{backends.SDRAM_DQ_WIDTHS}; no SDRAM backend was instantiated"
        )
        return [], ""
    skip = ("dq", "clk", "ldqm", "udqm", "dqm")
    pins = ",\n".join(
        f"\t\t\to_dram_{key} => {port.name}"
        for key, port in pin_map.items()
        if key not in skip
    )
    dqm_lines = _dqm_assignments(pin_map)
    mem = spec.plan.get("mem")
    tck_ps = round(float(mem.period_ns) * 1000) if mem else 0
    fields = {
        "dq": dq.width,
        "dqm": dq.width // 8,
        "tck_ps": tck_ps,
        "chip": spec.chip_packages.get("sdram", ""),
        "pins": pins,
        "dq_name": dq.name,
        "dq_hi": dq.width - 1,
    }
    body = backends.template("sdram_body").format(**fields)
    clk = pin_map.get("clk")
    extra = [f"\t{clk.name} <= clk_mem_pin;"] if clk else []
    return (
        backends.template("sdram_signals")
        .format(**fields)
        .rstrip()
        .split("\n"),
        body + "\n".join([*dqm_lines, *extra]) + "\n",
    )


def _dqm_assignments(pin_map: dict[str, Port]) -> list[str]:
    """Liga a máscara de bytes interna aos pinos da placa.

    Parameters
    ----------
    pin_map : dict of {str: Port}
        As portas de SDRAM por tipo.

    Returns
    -------
    list of str
        `DRAM_LDQM <= dqm(0)` e assim por diante.
    """
    if "dqm" in pin_map:
        return [f"\t{pin_map['dqm'].name} <= dqm;"]
    return [
        f"\t{pin_map[key].name} <= dqm({i});"
        for i, key in enumerate(("ldqm", "udqm"))
        if key in pin_map
    ]


_NOR_PIN_MAP = {
    "addr": "o_fl_addr",
    "ce_n": "o_fl_ce_n",
    "oe_n": "o_fl_oe_n",
    "we_n": "o_fl_we_n",
    "rst_n": "o_fl_rst_n",
    "wp_n": "o_fl_wp_n",
    "ry": "i_fl_ry",
}
# Margem somada a cada tempo do chip NOR para o atraso de pino e de
# placa, em ns.
_NOR_MARGIN_NS = 5
# Largura do barramento de dados da FLASH NOR que o controlador atende.
_NOR_DQ_WIDTH = 8


def _nor_key(name: str) -> str:
    """Classifica uma porta da FLASH NOR pelo sufixo do nome.

    Parameters
    ----------
    name : str
        Nome da porta (`FL_CE_N`).

    Returns
    -------
    str
        `addr`, `dq`, `ce_n` e assim por diante.
    """
    return re.sub(r"^fl_?", "", name.lower())


def _nor_backend(spec: TopSpec, notes: list[str]) -> tuple[list[str], str]:
    """Escreve o backend de dispositivo da FLASH NOR de 8 bits.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    notes : list of str
        Recebe os avisos.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais e o corpo; vazios quando a placa não tem o chip.
    """
    pin_map = {_nor_key(p.name): p for p in _role(spec, "nor")}
    missing = [key for key in (*_NOR_PIN_MAP, "dq") if key not in pin_map]
    if missing or pin_map["dq"].width != _NOR_DQ_WIDTH:
        notes.append(
            f"W nor pins {missing or 'dq width'} missing or not 8 bits; "
            "no NOR backend was instantiated"
        )
        return [], ""
    core = spec.plan.get("core")
    period = math.floor(float(core.period_ns)) if core else 20
    pins = ",\n".join(
        f"\t\t\t{formal} => {pin_map[key].name}"
        for key, formal in _NOR_PIN_MAP.items()
    )
    fields = {
        "period_ns": period,
        "margin_ns": _NOR_MARGIN_NS,
        "chip": spec.chip_packages.get("nor", ""),
        "pins": pins,
        "dq_name": pin_map["dq"].name,
    }
    return (
        backends.template("nor_signals").rstrip().split("\n"),
        backends.template("nor_body").format(**fields),
    )


def _flash_backend(
    spec: TopSpec, fields: dict[str, Any], latency: dict[str, Any]
) -> tuple[list[str], str]:
    """Escreve o backend emulado da FLASH.

    Com o periférico `FLASH_CTRL`, acrescenta o chip de comandos
    (apagar, gravar, proteger) na porta B do armazenamento, que o
    carregador da JTAG toma enquanto o núcleo está parado.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    fields : dict of {str: Any}
        O `memory.rom` da plataforma.
    latency : dict of {str: Any}
        A latência da FLASH emulada.

    Returns
    -------
    tuple of (list of str, str)
        Sinais e corpo.
    """
    updatable = _flash_ctrl_id(spec) is not None
    names = ("st_address_b", "st_wren_b", "st_data_b")
    plain = ("ld_address_b", "ld_wren_b", "ld_data_b")
    addr, wren, data = names if updatable else plain
    body = backends.template("flash_body").format(
        first=latency.get("first", 24),
        nxt=latency.get("next", 4),
        addr_b=addr,
        wren_b=wren,
        data_b=data,
    )
    signals = backends.template("flash_signals").rstrip().split("\n")
    if updatable:
        body += "\n" + backends.template("flash_cmd_body").format(
            sector=int(fields.get("sector_bytes", 4096))
        )
        signals += backends.template("flash_cmd_signals").rstrip().split("\n")
    return signals, body


def _region_backend(
    spec: TopSpec, region: str, notes: list[str]
) -> tuple[list[str], str]:
    """Escreve o backend de uma região externa.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    region : str
        `rom` ou `ram`.
    notes : list of str
        Recebe os avisos.

    Returns
    -------
    tuple of (list of str, str)
        Sinais e corpo; vazios quando não há entidade para o backend.
    """
    backend, device = _external(spec)[region]
    fields = cast(dict[str, Any], spec.platform["memory"][region])
    latency = cast(dict[str, Any], fields.get("latency") or {})
    if region == "rom" and backend == "emulado":
        return _flash_backend(spec, fields, latency)
    if region == "ram" and backend == "emulado":
        body = backends.template("ram_body").format(
            latency=latency.get("first", 0)
        )
        return backends.template("ram_signals").rstrip().split("\n"), body
    if region == "ram" and device == "sdram":
        return _sdram_backend(spec, notes)
    if region == "rom" and device == "nor":
        return _nor_backend(spec, notes)
    notes.append(
        f"W region {region}: backend {backend} {device} has no entity yet "
        "(M.5); the region was left idle"
    )
    return [], ""


def render_top(spec: TopSpec) -> RenderedTop:
    """Escreve o topo da placa.

    Parameters
    ----------
    spec : TopSpec
        As portas, os relógios e a plataforma.

    Returns
    -------
    RenderedTop
        O texto do arquivo `.vhd` e os avisos.
    """
    notes: list[str] = []
    signals: list[str] = []
    bodies: list[str] = []
    for region in _external(spec):
        sigs, body = _region_backend(spec, region, notes)
        signals += sigs
        bodies.append(body)
    has_halt = "flash_halt" in "\n".join(signals)
    package = _package(spec.platform)
    header = [
        "-- " + "=" * 77,
        f"-- Topo da placa {spec.entity} (arquivo gerado, não edite)",
        "--",
        "-- Só liga o PLL, o SoC, um backend por região e o anel de pinos.",
        "-- " + "=" * 77,
        "",
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "use ieee.numeric_std.all;",
        "use work.utils_pkg.all;",
        f"use work.{package}.all;",
        "",
    ]
    arch = [
        f"architecture structural of {spec.entity} is",
        *_declarations(spec),
        *signals,
        "begin",
        "",
        *_pll_and_reset(spec, has_halt),
        *_soc_instance(spec),
        "\t-- Boot memory: bloco do FPGA lido pela busca de instrução.",
        "\tboot_inst : entity work.boot_memory",
        "\t\tgeneric map (size_bytes => BOOT_MEMORY_SIZE_BYTES)",
        "\t\tport map (",
        "\t\t\ti_address => if_addr(log2_exact(BOOT_MEMORY_SIZE_BYTES) - 3 "
        "downto 0), i_clk => clk_fetch,",
        "\t\t\ti_rden => if_rden, i_wren => '0', "
        "i_data => (others => '0'), o_q => boot_data",
        "\t\t);",
        "",
        *_io_wiring(spec),
        *bodies,
        "end architecture;",
        "",
    ]
    text = "\n".join([*header, *_entity(spec), *arch])
    return RenderedTop(text, notes)
