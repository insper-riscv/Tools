"""The subcommands that talk to the board over JTAG."""

import argparse
import sys
from pathlib import Path

from riscv_tools import (
    bin_to_image,
    boot_rom,
    mailbox,
    quartus_program,
    ram_dump,
    ram_target,
    ram_zero,
    rom_writer,
    uart_console,
)
from riscv_tools import display as display_mod
from riscv_tools.cli.common import jtag_link, project_root
from riscv_tools.settings import load_config


def cmd_write_rom(args: argparse.Namespace) -> None:
    """Implement `riscv-tools write-rom`.

    JTAG-writes a .mif into every ROM instance of the already-programmed
    board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.mif.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    rom_writer.write_rom(
        link, cfg["quartus"]["rom_mem_instances"], Path(args.mif)
    )


def cmd_zero_ram(args: argparse.Namespace) -> None:
    """Implement `riscv-tools zero-ram`.

    JTAG-clears the whole RAM instance of the already-programmed
    board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    ram_zero.zero_ram(
        link, ram_target.target_from_config(cfg), cfg["memory"]["ram_words"]
    )


def cmd_console(args: argparse.Namespace) -> None:
    """Implement `riscv-tools console`.

    Shows what the program prints through the JTAG UART while it runs,
    until interrupted or for args.seconds seconds, and gives it
    args.send first.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.seconds,
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
        Parsed CLI arguments — uses args.config, args.value, args.check.

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
        Parsed CLI arguments — uses args.config, args.out,
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
        link, ram_target.target_from_config(cfg), Path(args.out), words
    )


def cmd_program(args: argparse.Namespace) -> None:
    """Implement `riscv-tools program`.

    Compiles the Quartus project with the given .mif baked in as the
    ROM's init_file, then programs the board (the slow "full
    reconfigure" path).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root, args.mif.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)
    root = project_root(args)

    # BOOT_ROM (see riscv_tools.boot_rom) is only ever written here,
    # as part of this full compile — never JTAG-rewritten per test the
    # way FLASH (args.mif) is. Only meaningful for a project with a
    # 3-memory BOOT_ROM/FLASH/RAM split (paths.boot_rom set).
    boot_init: quartus_program.MifInit | None = None
    if cfg.get("paths", {}).get("boot_rom") and cfg["quartus"].get(
        "boot_rom_mif_target"
    ):
        build_dir = root / cfg["paths"]["build_dir"] / "boot_rom"
        boot_rom.build_boot_rom(
            cfg["toolchain"], cfg["paths"], root, build_dir
        )
        boot_rom_mif_path = build_dir / "boot_rom.mif"
        bin_to_image.bin_to_mif(
            build_dir / "boot_rom.bin",
            boot_rom_mif_path,
            depth=cfg["memory"]["boot_rom_words"],
        )
        boot_init = quartus_program.MifInit(
            target=cfg["quartus"]["boot_rom_mif_target"],
            path=boot_rom_mif_path,
        )

    quartus_program.full_reconfigure(
        project=quartus_program.QuartusProject(
            hardware_name=link.hardware_name,
            project_dir=root / cfg["quartus"]["project_dir"],
            project_name=cfg["quartus"]["project_name"],
            sof_file=cfg["quartus"]["sof_file"],
            stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        ),
        rom=quartus_program.MifInit(
            target=cfg["quartus"]["rom_mif_target"], path=Path(args.mif)
        ),
        boot_rom=boot_init,
    )


def cmd_mailbox(args: argparse.Namespace) -> None:
    """Implement `riscv-tools mailbox`.

    Reads the PASS/FAIL mailbox, or pulses the restart go-flag, on the
    already-programmed board.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.action ("read"
        or "pulse").

    Returns
    -------
    None
        For args.action == "read", prints "MAILBOX=<value>" to
        stdout.
    """
    cfg = load_config(args.config)
    link = jtag_link(cfg)

    if args.action == "read":
        print(f"MAILBOX={mailbox.read_configured(link, cfg)}")

    else:
        mailbox.pulse_configured(link, cfg)
