"""The `certify` and `certify-board` subcommands."""

import argparse
import sys

from riscv_tools import (
    certify,
)
from riscv_tools.certify.board import VERDICTS
from riscv_tools.cli.common import jtag_link, start_certification


def cmd_certify(args: argparse.Namespace) -> None:
    """Implement `riscv-tools certify`.

    Builds this project's own ACT4 target's self-checking ELFs (see
    act.target_config in config.yaml, and
    tools/riscv_build/act/rv32im-min/) via ACT4's own `make`
    (act.vendor_dir, a pinned vendor/riscv-arch-test submodule), then
    runs each one under cocotb/GHDL (see certify.run_suite). Requires
    the "sim" extra (cocotb), a RISC-V GCC toolchain (compile_exe in
    the ACT4 target's own test_config.yaml), and ACT4's own Ruby/
    Bundler/UDB toolchain (see vendor/riscv-arch-test/README.md
    "Prerequisites"), none of the real-hardware/JTAG toolchain this
    project's other subcommands need.

    Everything this invocation prints is also written to
    <run_log.logs_dir>/certification/latest.log (see run_log.start),
    a prior latest.log, if any, is archived under its own start
    timestamp first.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: uses args.config, args.root,
        args.extensions (overrides config.yaml's act.extensions when
        given).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if any test failed (or if no ELFs were produced at
        all; see certify.run_suite).
    """
    cfg, root = start_certification(args, "certification")
    build_dir = root / cfg["paths"]["build_dir"] / "act"

    results = certify.run_suite(cfg, root, build_dir)

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not results or not all(results.values()):
        sys.exit(1)


def cmd_certify_board(args: argparse.Namespace) -> None:
    """Implement `riscv-tools certify-board`.

    Builds the ACT4 ELFs of the SDRAM target and runs each one on the
    board: the host writes the ELF into the SDRAM through the debug
    port, restarts
    the core and reads the HTIF `tohost` word (see certify.board). The
    board must
    already be programmed with the SDRAM platform.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments: args.config, args.root, args.only
        (comma-separated ELF names, optional), args.extensions
        (overrides act.extensions) and
        args.skip_build.

    Returns
    -------
    None
        Prints a result per ELF and a summary. Exits with status 1 if
        any ELF did not pass.
    """
    cfg, root = start_certification(args, "certification-board")
    only = [n for n in args.only.split(",") if n] if args.only else None
    results = certify.run_suite_on_board(
        cfg,
        root,
        root / (cfg["paths"].get("build_dir") or "build") / "act-board",
        jtag_link(cfg),
        only,
        build=not args.skip_build,
    )

    print("\n=== Summary ===")
    for name, passed in results.items():
        verdict = VERDICTS[passed]
        print(f"  {verdict}  {name}")
    if not results or not all(v is True for v in results.values()):
        sys.exit(1)
