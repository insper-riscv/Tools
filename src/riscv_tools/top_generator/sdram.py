"""Escreve o backend de dispositivo da SDRAM, um controlador só.

Um chip de SDRAM atende até duas regiões ao mesmo tempo, a FLASH
(`instructions`) e a RAM (`data`), por mestres diferentes do mesmo
árbitro, sem segundo controlador e sem segundo conjunto de pinos.

O mestre A traz a porta de dados do SoC pela ponte de dados e
existe quando a RAM é `sdram`. O mestre I traz a face da FLASH e, com
`fetch`, a face de busca da RAM pela ponte de instruções, e existe
quando a FLASH é `sdram` ou a RAM é `sdram` com `fetch`. O mestre B é
a depuração pela JTAG e existe sempre.

Com as duas origens no mestre I, um `flash_arbiter` as junta, um pedido
por vez. O endereço de cada origem é levado ao endereço do chip pelo
`offset` da região (ver `riscv_tools.memory_map.chip_split`): uma
constante nos bits altos quando o deslocamento é alinhado e um somador
de constante caso contrário. Uma região sem `offset` mantém o endereço
do SoC, como antes.

Com a FLASH na SDRAM o mestre de depuração também comanda o `hold` do
núcleo, que o impede de executar enquanto a JTAG grava a FLASH.
"""

import re
from typing import Any, cast

from riscv_tools.board_ports import Port
from riscv_tools.memory_map import chip_split
from riscv_tools.memory_map.chip_split import ChipWindow
from riscv_tools.top_generator import backends
from riscv_tools.top_generator.spec import TopSpec, external, role_ports

_ACTIVE_LOW = ("cas", "ras", "we", "cs")
_HOLD_PORT = ",\n\t\t\to_core_hold => core_hold"


def sdram_key(name: str) -> str:
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
    for base in _ACTIVE_LOW:
        if key == f"{base}n":
            return f"{base}_n"
    return key


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


def chip_address(signal: str, window: ChipWindow | None) -> str:
    """Escreve o endereço do chip a partir do endereço do SoC.

    Parameters
    ----------
    signal : str
        O sinal de 32 bits com o endereço do SoC.
    window : ChipWindow or None
        Onde a região fica no chip; `None` mantém o endereço.

    Returns
    -------
    str
        A expressão VHDL de 32 bits. Os bits acima do endereço de byte
        do chip ficam como estão, porque a ponte os ignora.
    """
    if window is None:
        return signal
    top = f"{signal}(31 downto SDRAM_BYTE_BITS)"
    low = f"{signal}({window.low_bits - 1} downto 0)"
    if window.aligned:
        high = (
            f"std_logic_vector(to_unsigned({window.fixed_high}, "
            f"SDRAM_BYTE_BITS - {window.low_bits}))"
        )
        return f"{top} & {high} & {low}"
    sign, value = (
        ("+", window.delta) if window.delta >= 0 else ("-", -window.delta)
    )
    return (
        f"{top} & std_logic_vector(resize(unsigned({low}), SDRAM_BYTE_BITS) "
        f"{sign} to_unsigned({value}, SDRAM_BYTE_BITS))"
    )


def _window_checks(windows: dict[str, ChipWindow]) -> str:
    """Escreve as asserções de elaboração dos bits fixos das janelas.

    Parameters
    ----------
    windows : dict of {str: ChipWindow}
        As janelas usadas pelo backend.

    Returns
    -------
    str
        Uma asserção por janela: a janela cabe no chip e a constante
        dos bits altos cabe nos bits que sobram.
    """
    lines: list[str] = []
    for name, window in windows.items():
        lines.append(
            f"\tassert SDRAM_BYTE_BITS >= {window.low_bits} "
            f'report "{name} is larger than the SDRAM chip" '
            "severity failure;"
        )
        if window.aligned:
            lines.append(
                f"\tassert {window.fixed_high} < 2 ** "
                f"(SDRAM_BYTE_BITS - {window.low_bits}) "
                f'report "{name} offset is beyond the SDRAM chip" '
                "severity failure;"
            )
    return "\n".join(lines) + ("\n\n" if lines else "")


def _uses(spec: TopSpec) -> tuple[bool, bool, bool]:
    """Diz quais regiões e quais portas usam a SDRAM.

    Parameters
    ----------
    spec : TopSpec
        O topo.

    Returns
    -------
    tuple of (bool, bool, bool)
        A FLASH está na SDRAM, a RAM está na SDRAM e a busca na RAM
        (`fetch`) está ligada.
    """
    regions = external(spec)
    rom = regions.get("rom", ("", ""))[1] == "sdram"
    ram = regions.get("ram", ("", ""))[1] == "sdram"
    memory = cast(dict[str, Any], spec.platform.get("memory") or {})
    entry = cast(dict[str, Any], memory.get("ram") or {})
    return rom, ram, ram and bool(entry.get("fetch"))


def _instruction_path(
    rom: bool, ram: bool, fetch: bool
) -> tuple[list[str], str]:
    """Escreve o caminho de instruções até o mestre I do árbitro.

    Parameters
    ----------
    rom : bool
        A FLASH está na SDRAM.
    ram : bool
        A RAM está na SDRAM.
    fetch : bool
        A porta de instruções alcança a RAM.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais e o texto da ligação, sem os endereços do chip.
    """
    if not (rom or fetch):
        tie = (
            "\tri_ready <= '0';\n\tri_rdata <= (others => '0');\n"
            "\tri_rdx <= (others => '0');\n\n"
            if ram
            else ""
        )
        return [], backends.template("sdram_instr_idle") + tie
    signals = backends.template("sdram_instr_signals").rstrip().split("\n")
    if rom and fetch:
        return signals, backends.template("sdram_instr_mux")
    source = "fl" if rom else "ri"
    face = (
        f"\tins_addr <= {source}_addr_c;\n"
        f"\tins_rden <= {source}_rden;\n"
        f"\tins_line <= {source}_line;\n"
        f"\tins_adv <= {source}_adv;\n"
        f"\t{source}_ready <= ins_ready;\n"
        f"\t{source}_rdata <= ins_rdata;\n"
        f"\t{source}_rdx <= ins_rdx;\n"
    )
    other = (
        "\tri_ready <= '0';\n\tri_rdata <= (others => '0');\n"
        "\tri_rdx <= (others => '0');\n"
        if rom and ram
        else ""
    )
    return signals, face + other + "\n"


def _address_lines(
    windows: dict[str, ChipWindow], rom: bool, ram: bool, fetch: bool
) -> tuple[list[str], str]:
    """Escreve a tradução dos endereços do SoC para os do chip.

    Parameters
    ----------
    windows : dict of {str: ChipWindow}
        As janelas declaradas pela plataforma.
    rom : bool
        A FLASH está na SDRAM.
    ram : bool
        A RAM está na SDRAM.
    fetch : bool
        A porta de instruções alcança a RAM.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais de endereço do chip e as atribuições.
    """
    signals: list[str] = []
    lines: list[str] = []
    wanted = (
        ("rd_addr", "rd_addr_c", "RAM", ram, False),
        ("fl_addr", "fl_addr_c", "FLASH", rom, True),
        ("ri_addr", "ri_addr_c", "RAM", fetch, True),
    )
    for source, target, region, active, extra in wanted:
        if not active:
            continue
        if extra:
            signals.append(
                f"\tsignal {target} : std_logic_vector(31 downto 0);"
            )
        lines.append(
            f"\t{target} <= {chip_address(source, windows.get(region))};"
        )
    return signals, "\n".join(lines) + "\n\n"


def _template_lines(name: str, wanted: bool) -> list[str]:
    """Lê as linhas de um modelo de sinais, se o backend as pede.

    Parameters
    ----------
    name : str
        O modelo, sem a extensão.
    wanted : bool
        Se o backend usa o modelo.

    Returns
    -------
    list of str
        As linhas do modelo; vazia quando não é pedido.
    """
    return backends.template(name).rstrip().split("\n") if wanted else []


def _fields(
    spec: TopSpec, pin_map: dict[str, Port], rom: bool
) -> dict[str, Any]:
    """Monta os campos dos modelos do controlador.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    pin_map : dict of {str: Port}
        As portas de SDRAM por tipo.
    rom : bool
        A FLASH está na SDRAM, e o mestre de depuração leva o `hold`.

    Returns
    -------
    dict of {str: Any}
        Os campos de `sdram_signals` e `sdram_body`.
    """
    dq = pin_map["dq"]
    skip = ("dq", "clk", "ldqm", "udqm", "dqm")
    pins = ",\n".join(
        f"\t\t\to_dram_{key} => {port.name}"
        for key, port in pin_map.items()
        if key not in skip
    )
    mem = spec.plan.get("mem")
    return {
        "dq": dq.width,
        "dqm": dq.width // 8,
        "tck_ps": round(float(mem.period_ns) * 1000) if mem else 0,
        "chip": spec.chip_packages.get("sdram", ""),
        "pins": pins,
        "dq_name": dq.name,
        "dq_hi": dq.width - 1,
        "hold_port": _HOLD_PORT if rom else "",
    }


def _windows_used(
    spec: TopSpec, rom: bool, ram: bool, notes: list[str]
) -> dict[str, ChipWindow]:
    """Dá as janelas das regiões na SDRAM e avisa dos somadores.

    Parameters
    ----------
    spec : TopSpec
        O topo.
    rom : bool
        A FLASH está na SDRAM.
    ram : bool
        A RAM está na SDRAM.
    notes : list of str
        Recebe um aviso por janela não alinhada.

    Returns
    -------
    dict of {str: ChipWindow}
        As janelas usadas, por região.
    """
    windows = {
        name: window
        for name, window in chip_split.windows(spec.platform).items()
        if (name == "FLASH" and rom) or (name == "RAM" and ram)
    }
    notes += [
        f"W sdram region {name}: the offset is not a multiple of its "
        "window, so the chip address has a constant adder"
        for name, window in windows.items()
        if not window.aligned
    ]
    return windows


def _body(
    parts: tuple[bool, bool, bool],
    windows: dict[str, ChipWindow],
    fields: dict[str, Any],
) -> tuple[list[str], str]:
    """Junta os sinais e o corpo das partes do backend.

    Parameters
    ----------
    parts : tuple of (bool, bool, bool)
        A FLASH, a RAM e o `fetch`, como em `_uses`.
    windows : dict of {str: ChipWindow}
        As janelas usadas.
    fields : dict of {str: Any}
        Os campos dos modelos.

    Returns
    -------
    tuple of (list of str, str)
        Os sinais e o corpo, sem as ligações dos pinos.
    """
    rom, ram, fetch = parts
    instr_signals, instr = _instruction_path(rom, ram, fetch)
    addr_signals, addr = _address_lines(windows, rom, ram, fetch)
    signals = [
        *backends.template("sdram_signals")
        .format(**fields)
        .rstrip()
        .split("\n"),
        *_template_lines("sdram_ram_signals", ram),
        *_template_lines("sdram_flash_signals", rom),
        *_template_lines("sdram_hold_signals", rom),
        *instr_signals,
        *addr_signals,
    ]
    data = "sdram_data_bridge" if ram else "sdram_data_idle"
    flash_face = "\tfl_busy <= fl_rden and not fl_ready;\n\n" if rom else ""
    body = (
        _window_checks(windows)
        + addr
        + backends.template(data)
        + instr
        + (backends.template("sdram_instr_bridge") if (rom or fetch) else "")
        + flash_face
        + (backends.template("sdram_hold") if rom else "")
        + backends.template("sdram_body").format(**fields)
    )
    return signals, body


def sdram_backend(spec: TopSpec, notes: list[str]) -> tuple[list[str], str]:
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
        serve (largura de dados diferente de 16 ou 32 bits).
    """
    pin_map = {sdram_key(p.name): p for p in role_ports(spec, "sdram")}
    width = pin_map["dq"].width
    if width not in backends.SDRAM_DQ_WIDTHS:
        notes.append(
            f"W sdram data width {width} is not one of "
            f"{backends.SDRAM_DQ_WIDTHS}; no SDRAM backend was instantiated"
        )
        return [], ""
    rom, ram, fetch = _uses(spec)
    windows = _windows_used(spec, rom, ram, notes)
    signals, body = _body(
        (rom, ram, fetch), windows, _fields(spec, pin_map, rom)
    )
    clk = pin_map.get("clk")
    extra = [f"\t{clk.name} <= clk_mem_pin;"] if clk else []
    dqm_lines = _dqm_assignments(pin_map)
    return signals, body + "\n".join([*dqm_lines, *extra]) + "\n"
