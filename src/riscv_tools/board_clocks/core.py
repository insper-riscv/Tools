"""Decide quais relógios o SoC pede e com que frequência e fase.

O PLL, o `.sdc` e o topo leem este plano, de modo que cada relógio é
decidido uma só vez. As frequências saem do `platform.yaml` (`clocks`),
o teto do relógio de memória sai do chip do catálogo e a fase do
relógio que sai pelo pino sai do `board.yaml`.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, cast

from riscv_tools.board_inputs import BoardInputs, InputError

# Nome único da instância do PLL em todos os topos gerados; o `.sdc`
# não varia com ele.
PLL_INSTANCE = "pll_inst"
# Ordem das saídas do PLL.
ROLE_ORDER = ("mem", "mem_pin", "fetch", "core")


@dataclass(frozen=True)
class ClockRole:
    """Um relógio por papel.

    Attributes
    ----------
    role : str
        `mem`, `mem_pin`, `fetch` ou `core`.
    mhz : Fraction
        Frequência em MHz.
    phase_ps : int
        Fase em picossegundos contra a referência do PLL.
    """

    role: str
    mhz: Fraction
    phase_ps: int

    @property
    def period_ns(self) -> Fraction:
        """Período em nanossegundos."""
        return 1000 / self.mhz


@dataclass(frozen=True)
class ClockPlan:
    """Os relógios de uma geração.

    Attributes
    ----------
    reference_signal : str
        Porta do relógio de entrada que alimenta o PLL.
    reference_mhz : Fraction
        Frequência dessa entrada.
    roles : tuple of ClockRole
        Os relógios pedidos, na ordem das saídas do PLL.
    warnings : list of str
        Avisos (fase desconhecida).
    """

    reference_signal: str
    reference_mhz: Fraction
    roles: tuple[ClockRole, ...]
    warnings: list[str] = field(default_factory=lambda: [])

    def get(self, role: str) -> ClockRole | None:
        """Busca um relógio pelo papel.

        Parameters
        ----------
        role : str
            O papel.

        Returns
        -------
        ClockRole or None
            O relógio, ou `None` se a plataforma não o pede.
        """
        return next((c for c in self.roles if c.role == role), None)

    def index(self, role: str) -> int:
        """Dá o índice da saída do PLL de um papel.

        Parameters
        ----------
        role : str
            O papel, que deve existir.

        Returns
        -------
        int
            Posição entre as saídas.
        """
        return [c.role for c in self.roles].index(role)

    @property
    def min_period_ns(self) -> Fraction:
        """Menor período entre os relógios do SoC."""
        return min(c.period_ns for c in self.roles if c.role != "mem_pin")


def _fraction(value: Any, what: str) -> Fraction:
    """Converta um número do YAML em fração exata.

    Parameters
    ----------
    value : Any
        O valor lido.
    what : str
        Nome do campo, para a mensagem.

    Returns
    -------
    Fraction
        O valor positivo.

    Raises
    ------
    InputError
        Se o valor não é um número positivo.
    """
    try:
        out = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as error:
        raise InputError(f"{what}: {value!r} is not a number") from error
    if out <= 0:
        raise InputError(f"{what}: {value!r} must be positive")
    return out


def _device_memories(inputs: BoardInputs) -> list[str]:
    """Lista os tipos de dispositivo de memória que a plataforma usa.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    list of str
        Os valores de `device` dos backends `dispositivo`.
    """
    memory = cast(dict[str, Any], inputs.platform.get("memory") or {})
    out: list[str] = []
    for region in memory.values():
        if isinstance(region, dict):
            fields = cast(dict[str, Any], region)
            if fields.get("backend") == "dispositivo":
                out.append(str(fields.get("device")))
    return out


def _mem_mhz(inputs: BoardInputs, requested: Fraction) -> Fraction:
    """Limita o relógio do controlador pelo teto dos chips usados.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    requested : Fraction
        O `clocks.mem.mhz` da plataforma.

    Returns
    -------
    Fraction
        O menor entre o pedido e o `max_mhz` de cada chip.

    Raises
    ------
    InputError
        Se o pedido passa do teto de um chip (regra V7).
    """
    for name, chip in inputs.chips.items():
        limit = chip.get("max_mhz")
        if limit is not None and requested > _fraction(limit, name):
            raise InputError(
                f"E clocks.mem {requested} MHz exceeds chip {name} limit "
                f"({limit} MHz)"
            )
    return requested


def _mem_roles(
    inputs: BoardInputs, wanted: dict[str, Any], warnings: list[str]
) -> list[ClockRole]:
    """Monta os relógios do controlador de dispositivo e do pino.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.
    wanted : dict of {str: Any}
        O `clocks` da plataforma.
    warnings : list of str
        Recebe os avisos achados.

    Returns
    -------
    list of ClockRole
        `mem` e, com SDRAM, `mem_pin`; vazio sem dispositivo.
    """
    devices = _device_memories(inputs)
    if not devices:
        return []
    mem = _mem_mhz(inputs, _fraction(wanted["mem"]["mhz"], "clocks.mem"))
    roles = [ClockRole("mem", mem, 0)]
    if "sdram" in devices:
        sdram = cast(dict[str, Any], inputs.board["memories"]["sdram"])
        phase = sdram.get("clk_phase_ps")
        if phase is None:
            warnings.append(
                "W memories.sdram.clk_phase_ps is null; DRAM_CLK phase "
                "set to 0 until it is measured"
            )
        roles.append(ClockRole("mem_pin", mem, int(phase or 0)))
    return roles


def clock_plan(inputs: BoardInputs) -> ClockPlan:
    """Monta o plano de relógios.

    Parameters
    ----------
    inputs : BoardInputs
        Os dados da placa.

    Returns
    -------
    ClockPlan
        A referência e os relógios por papel.

    Raises
    ------
    InputError
        Se falta `clocks.core` ou um relógio passa do limite do chip.
    """
    wanted = cast(dict[str, Any], inputs.platform.get("clocks") or {})
    if "core" not in wanted:
        raise InputError("platform: clocks.core is required")
    board_clocks = cast(dict[str, Any], inputs.board["clocks"])
    reference = next(
        c
        for c in cast(list[dict[str, Any]], board_clocks["inputs"])
        if c["name"] == board_clocks["reference"]
    )
    warnings: list[str] = []
    roles = _mem_roles(inputs, wanted, warnings)
    for role in ("fetch", "core"):
        if role in wanted:
            fields = cast(dict[str, Any], wanted[role])
            roles.append(
                ClockRole(
                    role,
                    _fraction(fields["mhz"], f"clocks.{role}"),
                    int(fields.get("phase_ps", 0)),
                )
            )
    return ClockPlan(
        str(reference["signal"]),
        _fraction(reference["mhz"], "clocks.inputs"),
        tuple(roles),
        warnings,
    )
