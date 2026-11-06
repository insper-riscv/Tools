"""The subcommands that talk to the board over JTAG."""

import argparse
import sys
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    boot_memory,
    htif,
    quartus_program,
    ram_dump,
    ram_target,
    ram_zero,
    rom_writer,
    uart_console,
)
from riscv_tools import display as display_mod
from riscv_tools.board_inputs import board_idcode
from riscv_tools.cli.common import jtag_link, project_root
from riscv_tools.jtag import detect_jtag_hardware
from riscv_tools.settings import load_config


def cmd_write_rom(args: argparse.Namespace) -> None:
    """Implement `riscv-tools write-rom`.

    JTAG-writes a .mif into the ROM of the already-programmed board:
    into every instance listed, or through the FLASH loader, which also
    restarts the core (quartus.rom_write_method).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.mif.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    rom_writer.write_rom_configured(link, cfg, Path(args.mif))


def cmd_zero_ram(args: argparse.Namespace) -> None:
    """Implement `riscv-tools zero-ram`.

    JTAG-clears the whole RAM instance of the already-programmed
    board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    ram_zero.zero_ram(
        link,
        ram_target.target_from_config(cfg, link),
        cfg["memory"]["ram_words"],
    )


def cmd_console(args: argparse.Namespace) -> None:
    """Implement `riscv-tools console`.

    Shows what the program prints through the JTAG UART while it runs,
    until interrupted or for args.seconds seconds, and gives it
    args.send first.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.seconds,
        args.send, args.interactive.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)

    def show(chunk: bytes) -> None:
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()

    uart_console.read_console(
        link,
        show,
        seconds=args.seconds,
        send=args.send.encode(),
        typed=sys.stdin if args.interactive else None,
    )


def cmd_display(args: argparse.Namespace) -> None:
    """Implement `riscv-tools display`.

    Reads the seven-segment display register of the platform, or writes
    it first when args.value is given, and prints what it holds.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.value, args.check.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    if args.check:
        bad = display_mod.check_display(link, args.check)
        print(f"{args.check} writes read back, {bad} differences")
        if bad:
            sys.exit(1)
        return
    if args.value is None:
        value = display_mod.read_display(link)
    else:
        value = display_mod.write_display(link, int(args.value, 16))
    print(f"{value:06x}")


def cmd_dump_ram(args: argparse.Namespace) -> None:
    """Implement `riscv-tools dump-ram`.

    JTAG-saves the RAM of the already-programmed board to a .mif: the
    whole RAM instance of the FPGA, or, for a RAM in the SDRAM (too big
    to read whole), the args.words words from args.start_word.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.out,
        args.start_word, args.words.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    words = None
    if args.words is not None:
        words = list(range(args.start_word, args.start_word + args.words))
    ram_dump.dump_ram(
        link, ram_target.target_from_config(cfg, link), Path(args.out), words
    )


def _boot_init(
    cfg: dict[str, Any], root: Path
) -> quartus_program.MifInit | None:
    """Compila o BOOT_MEMORY e devolve a imagem a embutir.

    Parameters
    ----------
    cfg : dict of {str: Any}
        A configuração mesclada do projeto.
    root : Path
        A raiz do projeto.

    Returns
    -------
    MifInit or None
        A imagem do BOOT_MEMORY, ou `None` num projeto sem a divisão
        BOOT_MEMORY/FLASH/RAM.
    """
    if not (
        cfg.get("paths", {}).get("boot_memory")
        and cfg["quartus"].get("boot_memory_mif_target")
    ):
        return None
    build_dir = root / cfg["paths"]["build_dir"] / "boot_memory"
    boot_memory.build_boot_memory(
        cfg["toolchain"],
        cfg["paths"],
        root,
        build_dir,
        boot_memory.BootMemoryOptions(base=cfg["isa"]["base"]),
    )
    path = build_dir / "boot_memory.mif"
    bin_to_image.bin_to_mif(
        build_dir / "boot_memory.bin",
        path,
        depth=cfg["memory"]["boot_memory_words"],
    )
    return quartus_program.MifInit(
        target=cfg["quartus"]["boot_memory_mif_target"], path=path
    )


def _cable(
    args: argparse.Namespace,
    cfg: dict[str, Any],
    root: Path,
    options: quartus_program.CompileOptions,
) -> str:
    """Escolhe o cabo de programação.

    Parameters
    ----------
    args : argparse.Namespace
        Uses args.board and args.boards_dir.
    cfg : dict of {str: Any}
        A configuração do projeto.
    root : Path
        A raiz do projeto.
    options : CompileOptions
        As opções; sem programar não há cabo.

    Returns
    -------
    str
        O nome do cabo, ou vazio quando a placa não é programada. Com
        `--board` vale o IDCODE da placa; sem ele, o do projeto.
    """
    if not options.programs:
        return ""
    if args.board:
        boards = Path(args.boards_dir) if args.boards_dir else root / "boards"
        idcode = board_idcode(boards, args.board)
        return detect_jtag_hardware(f"0x{idcode}")
    return jtag_link(cfg).hardware_name


def cmd_program(args: argparse.Namespace) -> None:
    """Implement `riscv-tools program`.

    Compiles the Quartus project (with the .mif baked in as the ROM's
    init_file, when given) and programs the board, the slow "full
    reconfigure" path. `--seed`, `--generic`, `--stop-after` and
    `--compile-only` replace the per-platform `*_synth.tcl` scripts, and
    `--board` picks the cable by the IDCODE of that board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.root, args.mif,
        args.board, args.boards_dir, args.project_dir,
        args.project_name, args.seed, args.generic, args.stop_after,
        args.compile_only.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    root = project_root(args)
    options = quartus_program.CompileOptions(
        seed=args.seed,
        generics=quartus_program.parse_generics(args.generic),
        stop_after=args.stop_after,
        compile_only=args.compile_only,
    )
    if args.mif is None and options.programs:
        sys.exit(
            "program: the .mif is required unless --compile-only or "
            "--stop-after is given"
        )
    quartus = cfg["quartus"]
    name = args.project_name or quartus["project_name"]
    sof = (
        f"output_files/{name}.sof"
        if args.project_name
        else quartus["sof_file"]
    )
    quartus_program.full_reconfigure(
        project=quartus_program.QuartusProject(
            hardware_name=_cable(args, cfg, root, options),
            project_dir=root / (args.project_dir or quartus["project_dir"]),
            project_name=name,
            sof_file=sof,
            stale_cache_dirs=quartus["stale_cache_dirs"],
        ),
        rom=(
            quartus_program.MifInit(
                target=quartus["rom_mif_target"], path=Path(args.mif)
            )
            if args.mif
            else None
        ),
        boot_memory=_boot_init(cfg, root) if args.mif else None,
        options=options,
    )


def cmd_htif(args: argparse.Namespace) -> None:
    """Implement `riscv-tools htif`.

    Reads the tohost word, or writes the fromhost restart word, on the
    already-programmed board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.action ("read"
        or "restart").

    Returns
    -------
    None
        For args.action == "read", prints "TOHOST=<value>" to
        stdout.
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)

    if args.action == "read":
        print(f"TOHOST={htif.read_tohost_configured(link, cfg)}")

    else:
        htif.pulse_fromhost_configured(link, cfg)
