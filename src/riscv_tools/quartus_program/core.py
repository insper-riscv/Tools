"""Compile the whole Quartus project and program the board (slow)."""

import re
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.proc import run_streaming

# Thin alias: this module's own callers/docs refer to "_run_captured";
# see riscv_tools.proc.run_streaming for the streaming/classification
# rationale, shared with jtag.link.run.
_run_captured = run_streaming

# Script de compilação único de todos os projetos, no lugar dos
# <projeto>_synth.tcl de cada plataforma.
COMPILE_TCL = Path(__file__).resolve().parent / "tcl" / "compile.tcl"
STOP_POINTS = ("map", "fit", "sta")
_GENERIC = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=([0-9]+)$")
DEFAULT_SEED = 5


@dataclass(frozen=True)
class CompileOptions:
    """Opções da compilação além do fluxo completo de sempre.

    Attributes
    ----------
    seed : int or None
        Semente do posicionamento; `None` mantém a do projeto.
    generics : tuple of (str, int)
        Generics do topo trocados só nesta compilação.
    stop_after : str or None
        `map`, `fit` ou `sta`; `None` roda o fluxo inteiro.
    compile_only : bool
        Não programa a placa depois de compilar.
    """

    seed: int | None = None
    generics: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    stop_after: str | None = None
    compile_only: bool = False

    @property
    def uses_script(self) -> bool:
        """Diz se a compilação passa pelo script único."""
        return bool(self.seed is not None or self.generics or self.stop_after)

    @property
    def programs(self) -> bool:
        """Diz se a placa é programada depois da compilação."""
        return not self.compile_only and self.stop_after is None


def parse_generics(items: list[str]) -> tuple[tuple[str, int], ...]:
    """Lê os `NOME=VALOR` da linha de comando.

    Parameters
    ----------
    items : list of str
        Os argumentos `--generic`.

    Returns
    -------
    tuple of (str, int)
        Nome e valor de cada generic.

    Raises
    ------
    ValueError
        Se um argumento não é `NOME=inteiro`.
    """
    out: list[tuple[str, int]] = []
    for item in items:
        found = _GENERIC.match(item)
        if found is None:
            raise ValueError(f"--generic {item!r}: expected NAME=INTEGER")
        out.append((found.group(1), int(found.group(2))))
    return tuple(out)


def compile_command(project_name: str, options: CompileOptions) -> list[str]:
    """Monta o comando de compilação.

    Parameters
    ----------
    project_name : str
        A revisão do projeto.
    options : CompileOptions
        As opções.

    Returns
    -------
    list of str
        O fluxo direto do Quartus sem opções, ou o script único com
        semente, ponto de parada e generics.
    """
    if not options.uses_script:
        return ["quartus_sh", "--flow", "compile", project_name]
    seed = DEFAULT_SEED if options.seed is None else options.seed
    return [
        "quartus_sh",
        "-t",
        str(COMPILE_TCL),
        project_name,
        str(seed),
        options.stop_after or "full",
        *(f"{name}={value}" for name, value in options.generics),
    ]


def program_only(hardware_name: str, project_dir: Path, sof_file: str) -> None:
    """Reprogram the board from the existing .sof, without recompiling.

    Takes about 10 s instead of the minutes a full compile takes, and is
    enough when the design has not changed (only the ROM content, which
    is loaded over JTAG). The board boots with the ROM baked into the
    .sof, so the caller still has to write the current test's ROM and
    pulse the restart flag afterwards.

    Parameters
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware), pinned explicitly via
        quartus_pgm's -c so a second board's cable can't be picked by
        mistake.
    project_dir : Path
        Path to the Quartus project directory (quartus.project_dir in
        the project's config.yaml).
    sof_file : str
        Path (relative to project_dir) to the compiled .sof, passed to
        quartus_pgm (quartus.sof_file).

    Returns
    -------
    None

    Raises
    ------
    FileNotFoundError
        sof_file doesn't exist (e.g. a previous full_reconfigure got
        interrupted after its stale_cache_dirs cleanup but before the
        Assembler produced a new one); nothing to reprogram from,
        caller should fall back to full_reconfigure instead.
    """
    # The memory instances may get other indices with the new design.
    mem_edit.invalidate()
    sof_path = project_dir / sof_file
    if not sof_path.is_file():
        raise FileNotFoundError(
            f"{sof_path} does not exist; need a full compile first"
        )
    pgm_cmd = [
        "quartus_pgm",
        "-c",
        hardware_name,
        "-m",
        "JTAG",
        "-o",
        f"p;{sof_path}",
    ]
    _run_captured(pgm_cmd)


@dataclass(frozen=True)
class QuartusProject:
    """The Quartus project settings a full compile and program needs.

    Attributes
    ----------
    hardware_name : str
        The JTAG cable name to program with (see
        jtag.detect_jtag_hardware), pinned explicitly via quartus_pgm's
        -c so a second board's cable can't be picked by mistake.
    project_dir : Path
        Path to the Quartus project directory (quartus.project_dir in
        the project's config.yaml).
    project_name : str
        Quartus project/revision name passed to `quartus_sh --flow
        compile` (quartus.project_name).
    sof_file : str
        Path (relative to project_dir) to the compiled .sof, passed to
        quartus_pgm (quartus.sof_file).
    stale_cache_dirs : list of str
        Directory names (relative to project_dir) to delete before
        compiling, since Quartus' incremental build cache doesn't
        track init_file content as a project source
        (quartus.stale_cache_dirs).
    """

    hardware_name: str
    project_dir: Path
    project_name: str
    sof_file: str
    stale_cache_dirs: list[str]


@dataclass(frozen=True)
class MifInit:
    """A .mif baked in as a memory's initial content.

    Attributes
    ----------
    target : str
        Path (relative to project_dir) the memory megafunction reads
        its init_file from at compile time (e.g.
        quartus.rom_mif_target); `path` is copied here before
        compiling.
    path : Path
        Path to the .mif to bake in as the memory's initial content.
    """

    target: str
    path: Path


def full_reconfigure(
    project: QuartusProject,
    rom: MifInit | None,
    boot_memory: MifInit | None = None,
    options: CompileOptions | None = None,
) -> None:
    """Compile the whole Quartus project and program the board.

    Bakes rom.path in as the ROM's init_file, then programs the board.
    It is the slow path: run it once up front to get a baseline
    bitstream, and again as a fallback when a JTAG-reloaded test times
    out.

    Parameters
    ----------
    project : QuartusProject
        The Quartus project to compile and program.
    rom : MifInit or None
        The .mif to bake in as the ROM's initial content; None leaves
        the project's own.
    boot_memory : MifInit, optional
        The .mif to bake in as the shared bootloader's initial content
        (quartus.boot_memory_mif_target), only for a project with a
        BOOT_MEMORY/FLASH/RAM split. It is written only by this full
        compile, never per test.
    options : CompileOptions, optional
        Seed, generics, stop point and compile-only; without them the
        flow is the direct `quartus_sh --flow compile` plus programming.

    Returns
    -------
    None
    """
    # The memory instances may get other indices with the new design.
    mem_edit.invalidate()
    project_dir = project.project_dir
    for init in (rom, boot_memory):
        if init is not None:
            target = project_dir / init.target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(init.path, target)

    for stale in project.stale_cache_dirs:
        shutil.rmtree(project_dir / stale, ignore_errors=True)

    # Compile and program run as ONE bash -c chain, not as two
    # subprocess.run() calls: quartus_pgm launched on its own right
    # after quartus_sh fails with "Can't scan JTAG chain" (error 87),
    # whatever the delay between the two, while the same two commands
    # in a single shell succeed.
    options = options or CompileOptions()
    compile_cmd = compile_command(project.project_name, options)
    pgm_cmd = [
        "quartus_pgm",
        "-c",
        project.hardware_name,
        "-m",
        "JTAG",
        "-o",
        f"p;{project_dir / project.sof_file}",
    ]
    chain = [shlex.join(compile_cmd)]
    if options.programs:
        chain.append(shlex.join(pgm_cmd))
    script = f"cd {shlex.quote(str(project_dir))} && " + " && ".join(chain)
    _run_captured(["bash", "-c", script])
