"""The `generate-header` and `generate-golden` subcommands."""

import argparse
import sys
from pathlib import Path

from riscv_tools import (
    golden_generator,
    mailbox,
)
from riscv_tools.cli.common import project_root
from riscv_tools.cli.project import spike_target
from riscv_tools.settings import load_config


def cmd_generate_header(args: argparse.Namespace) -> None:
    """Implement `riscv-tools generate-header`.

    Writes rv32_test.h from the project's own config.yaml (see
    mailbox.write_header).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root, args.out.

    Returns
    -------
    None
        Prints the path written to stdout.
    """
    cfg = load_config(args.config)
    root = project_root(args)
    out_path = (
        Path(args.out)
        if args.out
        else root / cfg["paths"]["include_dir"] / "rv32_test.h"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mailbox.write_header(cfg["memory"]["mailbox_addr"], out_path)
    print(f"Wrote {out_path}")


def cmd_generate_golden(args: argparse.Namespace) -> None:
    """Implement `riscv-tools generate-golden`.

    Runs an ELF under Spike and writes a golden JSON snapshot of a RAM
    byte range (see golden_generator.generate_golden).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.elf, args.march,
        args.out, and either args.symbol (resolved via
        golden_generator.symbol_range) or both args.start/args.end
        (parsed with base 0, so "0x10010" or "65552" both work) — the
        argument parser enforces exactly one of these two is given.
        Both forms are ABSOLUTE ELF addresses (whatever `nm`/`objdump`
        would print for the symbol) — memory.ram_base is subtracted
        automatically so the golden JSON's own keys come out
        RAM-relative either way (see golden_generator.generate_golden).

    Returns
    -------
    None
        Prints the number of bytes written to stdout.
    """
    if bool(args.symbol) == bool(args.start or args.end):
        print(
            "error: pass either --symbol, or both --start and --end (not both "
            "forms)",
            file=sys.stderr,
        )
        sys.exit(2)
    if bool(args.start) != bool(args.end):
        print(
            "error: --start and --end must be given together", file=sys.stderr
        )
        sys.exit(2)

    cfg = load_config(args.config)
    nm_bin = cfg["toolchain"]["nm"]
    elf_path = Path(args.elf)

    if args.symbol:
        addr_start, addr_end = golden_generator.symbol_range(
            nm_bin, elf_path, args.symbol
        )
    else:
        addr_start, addr_end = int(args.start, 0), int(args.end, 0)

    golden = golden_generator.generate_golden(
        spike_target(cfg, args.march),
        elf_path,
        (addr_start, addr_end),
        ram_base=cfg["memory"]["ram_base"],
        timeout_s=cfg["emulator"]["timeout_s"],
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    golden_generator.write_golden_json(golden, out_path)
    print(f"Wrote {out_path} ({len(golden)} bytes)")
