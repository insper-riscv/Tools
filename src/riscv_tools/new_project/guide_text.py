"""The short help the command prints when the project is ready."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from riscv_tools.memory_map import evaluate
from riscv_tools.memory_map.core import peripheral_list
from riscv_tools.new_project.layout import size_text

LANGUAGES = ("pt", "en")

_PT = """\
Projeto '{name}' pronto em {project}

Plataforma  {platform}
            (copiada de {template}, placa {board})
Perfil      {profile}
Memórias    {memories}
Periféricos
{peripherals}

Como mudar o projeto
  Edite {platform}
  e rode de novo, na pasta {repo}:
    riscv-tools generate-memory-map \\
      --platform {platform}
    riscv-tools check-memory-map \\
      --platform {platform}
  perfil       bloco `core` (`type`, `base`, `extensions`); o Tools
               infere o perfil da matriz, e os nomes válidos saem de
               riscv-tools profiles \\
                 --spec Core/profiles/matrix.yaml --format names
               (Interrupts e as outras extensões fora da matriz ficam
               na mesma lista `extensions`)
               A BOOT_MEMORY executa fence.i: o perfil precisa de
               zifencei, ou o boot reinicia para sempre
  memórias     `size` em `memory.instructions` e `memory.data`;
               mantenha `reserved` dentro dos dados e as bancas
               de `flash` dentro das instruções
  caches       `cache` (`size_bits`) do segmento de `memory`
  periféricos  um bloco de `peripherals` por periférico (a ordem é a dos
               índices), com `base`
               (endereço absoluto) e `size` (bytes de registradores);
               a janela é a menor potência de dois, de 16 bytes ou
               mais, e a base fica alinhada a ela. A ligação
               do VHDL de um periférico novo está no capítulo 11 de
               docs/pt-br/guide/nova-arquitetura.md

Próximos passos (na pasta do projeto, no computador com o Quartus)
  ./rt project doctor   confere arquivos, Quartus e cabo JTAG
  ./rt project build    compila o projeto do Quartus, sem gravar
  ./rt project flash <arquivo>.mif
                        grava o bitstream e um programa na placa
  ./rt project help     como rodar os testes e compilar um programa
                        seu
  O ./rt roda o riscv-tools na imagem dev_tools com o Quartus de
  /opt/altera_lite (outro caminho em QUARTUS_ROOT). Os arquivos ficam
  na pasta montada no contêiner, então continuam depois que ele
  termina.
"""

_EN = """\
Project '{name}' ready in {project}

Platform    {platform}
            (copied from {template}, board {board})
Profile     {profile}
Memories    {memories}
Peripherals
{peripherals}

How to change the project
  Edit {platform}
  and run again, in the folder {repo}:
    riscv-tools generate-memory-map \\
      --platform {platform}
    riscv-tools check-memory-map \\
      --platform {platform}
  profile      block `core` (`type`, `base`, `extensions`); the Tools
               infer the profile of the matrix, and the valid names
               come from
               riscv-tools profiles \\
                 --spec Core/profiles/matrix.yaml --format names
               (Interrupts and the other extensions outside the matrix
               stay in the same `extensions` list)
               The BOOT_MEMORY executes fence.i: the profile needs
               zifencei, or the boot restarts forever
  memories     `size` in `memory.instructions` and `memory.data`;
               keep `reserved` inside the data and the `flash`
               banks inside the instructions
  caches       `cache` (`size_bits`) of the `memory` segment
  peripherals  one `peripherals` block each (the order is the one of the
               indexes), with `base` (absolute
               address) and `size` (bytes of registers); the window
               is the smallest power of two, at least 16 bytes, and
               the base is aligned to it. The VHDL wiring
               of a new peripheral is in chapter 11 of
               docs/en/guide/nova-arquitetura.md

Next steps (in the project folder, on the computer with Quartus)
  ./rt project doctor   checks files, Quartus and the JTAG cable
  ./rt project build    builds the Quartus project, no programming
  ./rt project flash <file>.mif
                        programs the bitstream and a program
  ./rt project help     how to run the tests and compile a program
                        of your own
  ./rt runs riscv-tools in the dev_tools image with the Quartus of
  /opt/altera_lite (another path in QUARTUS_ROOT). The files stay in
  the folder mounted in the container, so they outlive it.
"""


@dataclass(frozen=True)
class Summary:
    """What the help tells about a project that was just created.

    Parameters
    ----------
    project : Path
        The folder of the project.
    repo : Path
        The `Insper-RISC-V` checkout.
    folder : Path
        Folder of the new platform, from the repository root.
    template : str
        Name of the platform it was copied from.
    board : str
        The board of the project.
    platform : dict of {str: Any}
        The new `platform.yaml`, parsed.
    """

    project: Path
    repo: Path
    folder: Path
    template: str
    board: str
    platform: dict[str, Any]


def _peripherals(platform: dict[str, Any]) -> str:
    """List the peripherals of a platform with their addresses.

    Parameters
    ----------
    platform : dict of {str: Any}
        The platform, parsed.

    Returns
    -------
    str
        One line per peripheral, or a dash when there is none.
    """
    lines = [
        f"  {item['name']:<12} 0x{int(item['base']):08X}"
        for item in peripheral_list(platform)
        if "base" in item
    ]
    return "\n".join(lines) or "  -"


def _memories(platform: dict[str, Any]) -> str:
    """Describe the ROM, the RAM and the caches in one line.

    Parameters
    ----------
    platform : dict of {str: Any}
        The platform, parsed.

    Returns
    -------
    str
        The sizes of the regions and the state of the caches.
    """
    sizes = [
        f"{r['name']} {size_text(int(evaluate(r['size'])))}"
        for r in platform["regions"]
        if r["name"] != "BOOT_MEMORY"
    ]
    memory = platform.get("memory", {})
    caches = [
        f"{name} "
        + (
            f"{memory[name]['size_bits']} bits"
            if memory.get(name, {}).get("enabled")
            else "off"
        )
        for name in ("icache", "dcache")
    ]
    return ", ".join([*sizes, *caches])


def render_help(language: str, summary: Summary) -> str:
    """Write the help for a project that was just created.

    Parameters
    ----------
    language : str
        `pt` or `en`.
    summary : Summary
        What to tell about the project.

    Returns
    -------
    str
        The help text.
    """
    platform = summary.platform
    return (_PT if language == "pt" else _EN).format(
        name=platform["platform"],
        project=summary.project,
        repo=summary.repo,
        folder=summary.folder,
        platform=summary.folder / "platform.yaml",
        template=summary.template,
        board=summary.board,
        profile=platform.get("profile", "-"),
        memories=_memories(platform),
        peripherals=_peripherals(platform),
    )
