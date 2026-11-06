"""Escreve o topo da placa, que só liga PLL, SoC, backends e pinos.

Contrato assumido com o SoC e os backends (documento 01, K1 a K9). Os
nomes de entidade e de porta ficam todos nas constantes abaixo, para
que ajustá-los ao `soc` e aos backends que o Memory publicar seja uma
troca neste arquivo e em nenhum outro.

| Entidade | Papel |
| :--- | :--- |
| `soc` | Núcleo, caches, interconector e periféricos, sem pino |
| `emulated_memory` | Backend `emulado` de uma região (K3 sob K2) |
| `sdram_backend` | Backend `dispositivo/sdram` (K2 sobre pinos) |
| `device_backend` | Backends `sram` e `nor` (K2 sobre pinos) |
| `tristate_buffer_1bit` | Anel de pinos de três estados |
"""

import re
from dataclasses import dataclass
from typing import Any, cast

from riscv_tools.board_clocks import PLL_INSTANCE, ClockPlan
from riscv_tools.board_ports import Port
from riscv_tools.memory_map import evaluate

SOC_ENTITY = "soc"
EMULATED_ENTITY = "emulated_memory"
SDRAM_ENTITY = "sdram_backend"
DEVICE_ENTITY = "device_backend"
TRISTATE_ENTITY = "tristate_buffer_1bit"
# Região do mapa que cada região externa do platform.yaml ocupa.
_REGION_NAME = {"rom": "FLASH", "ram": "RAM"}
_REGION_SIGNALS = (
    ("addr", 32),
    ("wdata", 32),
    ("be", 4),
    ("rden", 1),
    ("wren", 1),
    ("rdata", 32),
    ("ready", 1),
)
_SDRAM_ACTIVE_LOW = ("cas", "ras", "we", "cs")


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


def _dir(signal: str) -> str:
    """Dá o prefixo de direção de um sinal de região no lado do SoC.

    Parameters
    ----------
    signal : str
        `addr`, `rdata` e assim por diante.

    Returns
    -------
    str
        `i` para o que o SoC recebe, `o` para o que ele envia.
    """
    return "i" if signal in ("rdata", "ready") else "o"


def _back(signal: str) -> str:
    """Dá o prefixo de direção de um sinal de região no lado do backend.

    Parameters
    ----------
    signal : str
        `addr`, `rdata` e assim por diante.

    Returns
    -------
    str
        O oposto de `_dir`.
    """
    return "o" if _dir(signal) == "i" else "i"


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
        mode = {"in": "in   ", "out": "out  ", "inout": "inout"}[
            port.direction
        ]
        body.append(
            f"\t\t-- Porta {port.role} da placa.\n"
            f"\t\t{port.name} : {mode} {_vtype(port.width, port.vector)}"
        )
    lines += [";\n".join(body), "\t);", "end entity;", ""]
    return lines


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


def _external(spec: TopSpec) -> list[tuple[str, str, str]]:
    """Lista as regiões externas e seus backends.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of tuple of (str, str, str)
        Nome da região (`rom`, `ram`), backend e dispositivo.
    """
    memory = cast(dict[str, Any], spec.platform.get("memory") or {})
    out: list[tuple[str, str, str]] = []
    for key in ("rom", "ram"):
        fields = memory.get(key)
        if isinstance(fields, dict) and cast(dict[str, Any], fields).get(
            "external"
        ):
            f = cast(dict[str, Any], fields)
            out.append((key, str(f.get("backend")), str(f.get("device", ""))))
    return out


def _declarations(spec: TopSpec) -> list[str]:
    """Escreve os sinais da arquitetura.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    lines = [
        "\t-- Relógios por papel (K7) e travamento do PLL.",
        "\tsignal clk_core, clk_fetch, clk_mem, clk_mem_pin : std_logic;",
        "\tsignal pll_locked : std_logic;",
        "\t-- Reset do usuário normalizado para ativo em '1' e reset do SoC.",
        "\tsignal reset_active, rst_async, soc_rst : std_logic;",
        '\tsignal rst_sr : std_logic_vector(1 downto 0) := "11";',
    ]
    lines.extend(
        f"\tsignal soc_{port.name.lower()} : {_vtype(port.width, True)};"
        for port in spec.ports
        if port.role in ("leds", "switches", "keys")
    )
    digits = _role(spec, "display")
    if digits:
        lines.append(
            f"\tsignal soc_display : {_vtype(7 * len(digits), True)};"
        )
    for region, _, _ in _external(spec):
        for sig, width in _REGION_SIGNALS:
            lines.append(
                f"\tsignal {region}_{sig} : {_vtype(width, width > 1)};"
            )
    return lines


def _pll_instance(spec: TopSpec) -> list[str]:
    """Escreve a instância do PLL e a lógica de reset.

    Parameters
    ----------
    spec : TopSpec
        O topo.

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
    return [
        f"\treset_active <= {expr};",
        *aliases,
        f"\t{PLL_INSTANCE} : entity work.{spec.pll_module}",
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
        "\tsoc_rst <= rst_sr(1);",
        "",
    ]


def _polarity(spec: TopSpec) -> list[str]:
    """Escreve a normalização de polaridade dos papéis de E/S (K8).

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas.
    """
    lines = ["\t-- Polaridade normalizada para ativo em '1' (K8)."]
    for port in spec.ports:
        invert = "not " if port.active == "low" else ""
        name = port.name
        if port.role in ("switches", "keys"):
            lines.append(f"\tsoc_{name.lower()} <= {invert}{name};")
        elif port.role == "leds":
            lines.append(f"\t{name} <= {invert}soc_{name.lower()};")
    for i, port in enumerate(_role(spec, "display")):
        invert = "not " if port.active == "low" else ""
        lines.append(
            f"\t{port.name} <= {invert}soc_display"
            f"({7 * i + 6} downto {7 * i});"
        )
    return [*lines, ""]


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
    profile = str(spec.platform.get("profile", "")).lower()
    maps = [
        "i_clk_core => clk_core",
        "i_clk_fetch => clk_fetch",
        "i_clk_mem => clk_mem",
        "i_rst => soc_rst",
    ]
    for port in spec.ports:
        if port.role == "leds":
            maps.append(f"o_leds => soc_{port.name.lower()}")
        elif port.role in ("switches", "keys"):
            maps.append(f"i_{port.role} => soc_{port.name.lower()}")
    if _role(spec, "display"):
        maps.append("o_display => soc_display")
    for region, _, _ in _external(spec):
        maps += [
            f"{_dir(sig)}_{region}_{sig} => {region}_{sig}"
            for sig, _ in _REGION_SIGNALS
        ]
    lines = [f"\tsoc_inst : entity work.{SOC_ENTITY}"]
    if "zihpm" in profile:
        lines.append(
            "\t\tgeneric map (HPM_COUNTERS => HPM_COUNTERS, "
            "HPM_WIDTH => HPM_WIDTH)"
        )
    lines.append("\t\tport map (")
    lines.append(",\n".join(f"\t\t\t{m}" for m in maps))
    return [*lines, "\t\t);", ""]


def _region_size(spec: TopSpec, region: str) -> int:
    """Dá o tamanho em bytes da região do mapa de uma região externa.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    region : str
        `rom` ou `ram`.

    Returns
    -------
    int
        O tamanho.
    """
    wanted = _REGION_NAME[region]
    for entry in cast(
        list[dict[str, Any]], spec.platform.get("regions") or []
    ):
        if entry["name"] == wanted:
            return evaluate(entry["size"])
    return 0


def _emulated(spec: TopSpec, region: str) -> list[str]:
    """Escreve a instância de um backend emulado.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    region : str
        `rom` ou `ram`.

    Returns
    -------
    list of str
        As linhas.
    """
    fields = cast(dict[str, Any], spec.platform["memory"][region])
    generics = [f"SIZE_BYTES => {_region_size(spec, region)}"]
    latency = cast(dict[str, Any], fields.get("latency") or {})
    if latency:
        generics += [
            f"FIRST_LATENCY => {latency['first']}",
            f"NEXT_LATENCY => {latency['next']}",
        ]
    if "sector_bytes" in fields:
        generics.append(f"SECTOR_BYTES => {fields['sector_bytes']}")
    return [
        f"\t{region}_backend : entity work.{EMULATED_ENTITY}",
        "\t\tgeneric map (" + ", ".join(generics) + ")",
        "\t\tport map (i_clk => clk_core, i_rst => soc_rst, "
        + ", ".join(
            f"{_back(s)}_{s} => {region}_{s}" for s, _ in _REGION_SIGNALS
        )
        + ");",
        "",
    ]


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


def _sdram_pin_maps(pin_map: dict[str, Port]) -> list[str]:
    """Liga os sinais de comando e de máscara do backend aos pinos.

    Parameters
    ----------
    pin_map : dict of {str: Port}
        As portas de SDRAM por tipo (`addr`, `ldqm`, ...).

    Returns
    -------
    list of str
        As associações de porta, sem o dado (`dq`) e sem o relógio.
    """
    maps = [
        f"o_dram_{key} => {port.name}"
        for key, port in pin_map.items()
        if key not in ("dq", "clk", "ldqm", "udqm", "dqm")
    ]
    if "dqm" in pin_map:
        maps.append(f"o_dram_dqm => {pin_map['dqm'].name}")
    elif "ldqm" in pin_map:
        maps.append("o_dram_dqm(1 downto 0) => dqm_pins")
    else:
        maps.append("o_dram_dqm => open")
    return maps


def _sdram(spec: TopSpec, region: str) -> list[str]:
    """Escreve o backend de SDRAM e o anel de três estados do DQ.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    region : str
        A região (`ram`).

    Returns
    -------
    list of str
        As linhas.
    """
    ports = _role(spec, "sdram")
    pin_map = {_sdram_key(p.name): p for p in ports}
    dq = pin_map["dq"]
    maps = ["i_clk => clk_mem", "i_rst => soc_rst"]
    maps += [f"{_back(s)}_{s} => {region}_{s}" for s, _ in _REGION_SIGNALS]
    maps += _sdram_pin_maps(pin_map)
    maps += [
        "o_dram_dq_out => dq_out",
        "o_dram_dq_oe => dq_oe",
        "i_dram_dq_in => dq_in",
    ]
    chip = spec.chip_packages.get("sdram", "")
    lines = [
        f"\tsdram_inst : entity work.{SDRAM_ENTITY}",
        f"\t\tgeneric map (DQ_WIDTH => {dq.width})",
        "\t\tport map (",
        ",\n".join(f"\t\t\t{m}" for m in maps),
        "\t\t);",
        "",
        f"\t-- Anel de pinos: um buffer de três estados por bit de {dq.name}.",
        f"\tgen_dq : for i in 0 to {dq.width - 1} generate",
        f"\t\tdq_tri : entity work.{TRISTATE_ENTITY}",
        "\t\t\tport map (i_d => dq_out(i), i_enable => dq_oe, "
        f"o_d => {dq.name}(i));",
        "\tend generate;",
        f"\tdq_in <= {dq.name};",
    ]
    if "ldqm" in pin_map and "udqm" in pin_map:
        lines += [
            f"\t{pin_map['ldqm'].name} <= dqm_pins(0);",
            f"\t{pin_map['udqm'].name} <= dqm_pins(1);",
        ]
    if "clk" in pin_map:
        lines.append(f"\t{pin_map['clk'].name} <= clk_mem_pin;")
    if chip:
        lines.append(f"\t-- Tempos do chip: pacote {chip}.")
    return [*lines, ""]


def _device(spec: TopSpec, region: str, kind: str) -> list[str]:
    """Escreve o backend de SRAM ou de NOR.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    region : str
        A região.
    kind : str
        `sram` ou `nor`.

    Returns
    -------
    list of str
        As linhas.
    """
    maps = ["i_clk => clk_mem", "i_rst => soc_rst"]
    maps += [f"{_back(s)}_{s} => {region}_{s}" for s, _ in _REGION_SIGNALS]
    for port in _role(spec, kind):
        prefix = "i" if port.direction == "in" else "o"
        maps.append(f"{prefix}_pin_{port.name.lower()} => {port.name}")
    return [
        f"\t{kind}_inst : entity work.{DEVICE_ENTITY}",
        f'\t\tgeneric map (KIND => "{kind}")',
        "\t\tport map (",
        ",\n".join(f"\t\t\t{m}" for m in maps),
        "\t\t);",
        "",
    ]


def _backends(spec: TopSpec) -> list[str]:
    """Escreve uma instância de backend por região externa.

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
    for region, backend, device in _external(spec):
        if backend == "emulado":
            lines += _emulated(spec, region)
        elif device == "sdram":
            lines += _sdram(spec, region)
        else:
            lines += _device(spec, region, device)
    return lines


def _extra_signals(spec: TopSpec) -> list[str]:
    """Declara os sinais do anel de pinos de SDRAM.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    list of str
        As linhas, vazias sem SDRAM.
    """
    sdram = _role(spec, "sdram")
    dq = [p for p in sdram if _sdram_key(p.name) == "dq"]
    if not dq:
        return []
    width = dq[0].width
    return [
        "\t-- Dados da SDRAM separados em saída, habilitação e entrada.",
        f"\tsignal dq_out, dq_in : std_logic_vector({width - 1} downto 0);",
        "\tsignal dq_oe : std_logic;",
        "\tsignal dqm_pins : std_logic_vector(1 downto 0);",
    ]


def render_top(spec: TopSpec) -> str:
    """Escreve o topo da placa.

    Parameters
    ----------
    spec : TopSpec
        As portas, os relógios e a plataforma.

    Returns
    -------
    str
        O texto do arquivo `.vhd`.
    """
    header = [
        "-- " + "=" * 77,
        f"-- Topo da placa {spec.entity} (arquivo gerado, não edite)",
        "--",
        "-- Só liga o PLL, o SoC, um backend por região e o anel de pinos.",
        "-- " + "=" * 77,
        "",
        "library ieee;",
        "use ieee.std_logic_1164.all;",
        "",
    ]
    arch = [
        f"architecture structural of {spec.entity} is",
        *_declarations(spec),
        *_extra_signals(spec),
        "begin",
        "",
        *_pll_instance(spec),
        *_polarity(spec),
        *_soc_instance(spec),
        *_backends(spec),
        "end architecture;",
        "",
    ]
    return "\n".join([*header, *_entity(spec), *arch])
