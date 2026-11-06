"""Relatório de equivalência entre o projeto gerado e o escrito à mão.

A comparação é normalizada (documento 04, seção 8): pinos e padrões de
E/S como conjunto de (sinal, pino, padrão), restrições do `.sdc` como
conjunto de comandos com as variáveis expandidas e os conjuntos entre
chaves ordenados, e o PLL como frequência e fase por saída.
"""

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import PurePosixPath

_LOCATION = re.compile(r"^set_location_assignment PIN_(\w+) -to (\S+)\s*$")
_INSTANCE = re.compile(
    r"^set_instance_assignment -name (\w+) (\"[^\"]*\"|\S+) "
    r"-to (\S+|\"[^\"]*\")\s*$"
)
_GLOBAL = re.compile(r"^set_global_assignment -name (\w+) (.+?)\s*$")
_SOURCE_KINDS = ("VHDL_FILE", "VERILOG_FILE", "SYSTEMVERILOG_FILE", "QIP_FILE")
_PROJECT_KEYS = (
    "FAMILY",
    "DEVICE",
    "VHDL_INPUT_VERSION",
    "OPTIMIZATION_MODE",
    "SEED",
)
_FREQ = re.compile(r'\.output_clock_frequency(\d+)\("([\d.]+) MHz"\)')
_PHASE = re.compile(r'\.phase_shift(\d+)\("(-?\d+) ps"\)')
_REF = re.compile(r'\.reference_clock_frequency\("([\d.]+) MHz"\)')
_BRACES = re.compile(r"\{([^{}]*)\}")
_VARIABLE = re.compile(r"\$(\w+)")


@dataclass(frozen=True)
class HandWritten:
    """Os textos dos arquivos escritos à mão.

    Attributes
    ----------
    qsf : str
        O `.qsf`.
    sdc : str
        O `.sdc`.
    pll : str
        O PLL.
    """

    qsf: str
    sdc: str
    pll: str


@dataclass(frozen=True)
class Section:
    """Diferenças de um assunto.

    Attributes
    ----------
    name : str
        `pins`, `assignments`, `project`, `sources`, `constraints` ou
        `pll`.
    only_handwritten : list of str
        Itens que só o arquivo à mão tem.
    only_generated : list of str
        Itens que só o arquivo gerado tem.
    changed : list of str
        Itens nos dois com valores diferentes.
    """

    name: str
    only_handwritten: list[str] = field(default_factory=lambda: [])
    only_generated: list[str] = field(default_factory=lambda: [])
    changed: list[str] = field(default_factory=lambda: [])

    @property
    def equivalent(self) -> bool:
        """Verdadeiro quando o gerado cobre tudo o que o à mão tem."""
        return not (self.only_handwritten or self.changed)


@dataclass(frozen=True)
class Report:
    """O relatório de equivalência.

    Attributes
    ----------
    sections : list of Section
        Uma seção por assunto.
    """

    sections: list[Section]

    @property
    def equivalent(self) -> bool:
        """Verdadeiro quando nenhuma seção perde ou muda algo."""
        return all(s.equivalent for s in self.sections)

    def section(self, name: str) -> Section:
        """Busca uma seção.

        Parameters
        ----------
        name : str
            O assunto.

        Returns
        -------
        Section
            A seção.
        """
        return next(s for s in self.sections if s.name == name)

    def render(self) -> str:
        """Escreve o relatório em texto.

        Returns
        -------
        str
            Uma linha por diferença, agrupadas por assunto.
        """
        lines: list[str] = []
        for sec in self.sections:
            status = "equivalent" if sec.equivalent else "DIFFERENT"
            lines.append(f"[{sec.name}] {status}")
            lines += [f"  only handwritten: {i}" for i in sec.only_handwritten]
            lines += [f"  only generated: {i}" for i in sec.only_generated]
            lines += [f"  changed: {i}" for i in sec.changed]
        return "\n".join(lines) + "\n"


def _lines(text: str) -> list[str]:
    """Dá as linhas ativas de um arquivo do Quartus.

    Parameters
    ----------
    text : str
        O arquivo.

    Returns
    -------
    list of str
        As linhas que não são comentário nem vazias.
    """
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]


def _item(key: str, value: str) -> str:
    """Escreve um item de diferença sem repetir a chave.

    Parameters
    ----------
    key : str
        A chave.
    value : str
        O valor.

    Returns
    -------
    str
        `chave = valor`, ou só a chave quando o valor a repete.
    """
    return key if key == value else f"{key} = {value}"


def _diff(name: str, hand: dict[str, str], gen: dict[str, str]) -> Section:
    """Compara dois mapas chave para valor.

    Parameters
    ----------
    name : str
        O assunto.
    hand : dict of {str: str}
        O mapa do arquivo à mão.
    gen : dict of {str: str}
        O mapa do arquivo gerado.

    Returns
    -------
    Section
        As diferenças.
    """
    return Section(
        name,
        [_item(k, hand[k]) for k in hand if k not in gen],
        [_item(k, gen[k]) for k in gen if k not in hand],
        [
            f"{k}: {hand[k]} -> {gen[k]}"
            for k in hand
            if k in gen and hand[k] != gen[k]
        ],
    )


def pins_of(text: str) -> dict[str, str]:
    """Extrai (pino, padrão) de cada sinal de um `.qsf`.

    Parameters
    ----------
    text : str
        O `.qsf`.

    Returns
    -------
    dict of {str: str}
        Sinal para `PIN / padrão`.
    """
    pin: dict[str, str] = {}
    std: dict[str, str] = {}
    for line in _lines(text):
        loc = _LOCATION.match(line)
        if loc:
            pin[loc.group(2)] = loc.group(1)
        inst = _INSTANCE.match(line)
        if inst and inst.group(1) == "IO_STANDARD":
            std[inst.group(3)] = inst.group(2).strip('"')
    return {s: f"{p} / {std.get(s, '?')}" for s, p in pin.items()}


def _assignments(text: str, renames: dict[str, str]) -> dict[str, str]:
    """Extrai as atribuições por instância que não são padrão de E/S.

    Parameters
    ----------
    text : str
        O `.qsf`.
    renames : dict of {str: str}
        Trocas de texto a aplicar antes de comparar.

    Returns
    -------
    dict of {str: str}
        `NOME -to ALVO` para valor.
    """
    out: dict[str, str] = {}
    for raw in _lines(text):
        line = raw
        for old, new in renames.items():
            line = line.replace(old, new)
        inst = _INSTANCE.match(line)
        if inst and inst.group(1) != "IO_STANDARD" and inst.group(3) != "|":
            out[f"{inst.group(1)} -to {inst.group(3)}"] = inst.group(2)
    return out


def _globals(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Extrai as atribuições globais que importam e as fontes.

    Parameters
    ----------
    text : str
        O `.qsf`.

    Returns
    -------
    tuple of (dict, dict)
        As chaves do projeto e as fontes (nome do arquivo para tipo).
    """
    project: dict[str, str] = {}
    sources: dict[str, str] = {}
    for line in _lines(text):
        found = _GLOBAL.match(line)
        if not found or "-section_id" in line:
            continue
        key, value = found.group(1), found.group(2)
        if key in _PROJECT_KEYS:
            project[key] = value
        elif key in _SOURCE_KINDS:
            sources[PurePosixPath(value).name] = key
    return project, sources


def _sorted_braces(match: re.Match[str]) -> str:
    """Ordena os itens de um conjunto entre chaves.

    Parameters
    ----------
    match : re.Match
        O conjunto.

    Returns
    -------
    str
        O conjunto com os itens em ordem alfabética.
    """
    return "{" + " ".join(sorted(match.group(1).split())) + "}"


def _sdc_commands(text: str) -> dict[str, str]:
    """Normaliza um `.sdc` em um conjunto de comandos.

    Os `set <nome> <valor>` são expandidos nos usos seguintes e
    descartados, e os conjuntos entre chaves ficam ordenados.

    Parameters
    ----------
    text : str
        O `.sdc`.

    Returns
    -------
    dict of {str: str}
        Cada comando normalizado para ele mesmo.
    """
    variables: dict[str, str] = {}
    out: dict[str, str] = {}
    for raw in _lines(text):
        line = " ".join(raw.split())
        setter = re.match(r"^set (\w+) (.+)$", line)
        if setter and not line.startswith("set_"):
            variables[setter.group(1)] = _expand(setter.group(2), variables)
            continue
        line = _BRACES.sub(_sorted_braces, _expand(line, variables))
        out[line] = line
    return out


def _expand(line: str, variables: dict[str, str]) -> str:
    """Substitui `$nome` pelo valor guardado.

    Parameters
    ----------
    line : str
        O comando.
    variables : dict of {str: str}
        Os valores.

    Returns
    -------
    str
        O comando expandido.
    """
    return _VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), line)


def _pll(text: str) -> dict[str, str]:
    """Extrai frequência, fase e razão de cada saída de um PLL.

    Parameters
    ----------
    text : str
        O PLL em Verilog.

    Returns
    -------
    dict of {str: str}
        `outclk_<i>` para `MHz, fase, razão`.
    """
    ref = _REF.search(text)
    base = Fraction(ref.group(1)) if ref else None
    phases = {m.group(1): m.group(2) for m in _PHASE.finditer(text)}
    out: dict[str, str] = {}
    for match in _FREQ.finditer(text):
        index, mhz = match.group(1), Fraction(match.group(2))
        ratio = f"{mhz / base}" if base else "?"
        out[f"outclk_{index}"] = (
            f"{float(mhz):g} MHz, phase {phases.get(index, '?')} ps, "
            f"ratio {ratio}"
        )
    return out


def compare(
    hand: HandWritten,
    generated: HandWritten,
    renames: dict[str, str] | None = None,
    ignored_sources: frozenset[str] = frozenset(),
) -> Report:
    """Compara o projeto gerado com o escrito à mão.

    Parameters
    ----------
    hand : HandWritten
        Os arquivos à mão.
    generated : HandWritten
        Os arquivos gerados.
    renames : dict of {str: str}, optional
        Trocas de texto aplicadas ao arquivo à mão antes de comparar
        atribuições (o nome do módulo do PLL, por exemplo).
    ignored_sources : frozenset of str, optional
        Nomes de fonte que só existem de um lado por construção (o
        topo, o PLL e os pacotes de chip).

    Returns
    -------
    Report
        As seções `pins`, `assignments`, `project`, `sources`,
        `constraints` e `pll`.
    """
    swaps = renames or {}
    hand_project, hand_sources = _globals(hand.qsf)
    gen_project, gen_sources = _globals(generated.qsf)

    def keep(d: dict[str, str]) -> dict[str, str]:
        return {k: v for k, v in d.items() if k not in ignored_sources}

    sections = [
        _diff("pins", pins_of(hand.qsf), pins_of(generated.qsf)),
        _diff(
            "assignments",
            _assignments(hand.qsf, swaps),
            _assignments(generated.qsf, {}),
        ),
        _diff("project", hand_project, gen_project),
        _diff("sources", keep(hand_sources), keep(gen_sources)),
        _diff(
            "constraints",
            _sdc_commands(hand.sdc),
            _sdc_commands(generated.sdc),
        ),
        _diff("pll", _pll(hand.pll), _pll(generated.pll)),
    ]
    return Report(sections)
