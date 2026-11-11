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
  perfil       campo `profile`; os nomes válidos saem de
               riscv-tools profiles \\
                 --spec Core/profiles/matrix.yaml --format names
               (Zimop, Zicond, Interrupts e outras fora da matriz
               ficam em `extras`)
  memórias     `size` das regiões FLASH e RAM; mantenha `reserved`
               dentro da RAM e as bancas de `flash` dentro da FLASH
  caches       `memory.icache` e `memory.dcache` (`enabled`,
               `size_bits`)
  periféricos  uma linha de `peripherals` por periférico; a janela de
               256 MiB de cada um é 0x80000000 | id << 28. A ligação
               do VHDL de um periférico novo está no capítulo 11 de
               docs/pt-br/guide/nova-arquitetura.md

Próximos passos
  Projeto Quartus (já gerado): {repo}/build
  O Quartus não vem na imagem. Na máquina que o tem, compile e
  programe:
    riscv-tools --config {folder}/config.yaml \\
      --board {board} program --stop-after sta
    riscv-tools board lock --board {board} --wait -- \\
      riscv-tools --config {folder}/config.yaml \\
      --board {board} program <imagem.mif>
  Programas de teste: clone o repositório Tests ao lado de {repo}
  e siga docs/pt-br/guide/placa.md. Os arquivos ficam na pasta
  montada no contêiner (docker run -v "$PWD":/w ...), então
  continuam depois que ele termina.
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
  profile      field `profile`; the valid names come from
               riscv-tools profiles \\
                 --spec Core/profiles/matrix.yaml --format names
               (Zimop, Zicond, Interrupts and others outside the
               matrix go in `extras`)
  memories     `size` of the FLASH and RAM regions; keep `reserved`
               inside the RAM and the `flash` banks inside the FLASH
  caches       `memory.icache` and `memory.dcache` (`enabled`,
               `size_bits`)
  peripherals  one `peripherals` line each; the 256 MiB window of a
               peripheral is 0x80000000 | id << 28. The VHDL wiring
               of a new peripheral is in chapter 11 of
               docs/en/guide/nova-arquitetura.md

Next steps
  Quartus project (already generated): {repo}/build
  Quartus is not in the image. On the machine that has it, build
  and program:
    riscv-tools --config {folder}/config.yaml \\
      --board {board} program --stop-after sta
    riscv-tools board lock --board {board} --wait -- \\
      riscv-tools --config {folder}/config.yaml \\
      --board {board} program <image.mif>
  Test programs: clone the Tests repository next to {repo} and
  follow docs/en/guide/placa.md. The files stay in the folder
  mounted in the container (docker run -v "$PWD":/w ...), so they
  outlive it.
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
        if item.get("choice") == "ok"
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
