#!/usr/bin/env python3
"""Command-line entry point: ``riscv-tools --config <config.yaml> <subcommand> ...``.

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.)
— except `vhdl-sort`, which is pure file-content analysis and needs no
project config at all.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    golden_generator,
    mailbox,
    orchestrator,
    quartus_program,
    ram_dump,
    ram_zero,
    rom_writer,
    sim_runner,
    vhdl_sort,
)
from riscv_tools import c_to_asm as c_to_asm_mod
from riscv_tools import compiler as compiler_mod
from riscv_tools.jtag import JtagLink, detect_jtag_hardware
from riscv_tools.settings import load_config


def _link(cfg: dict[str, Any]) -> JtagLink:
    """Build a JtagLink for the currently connected cable and the project's chip.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config, uses quartus.jtag_device.

    Returns
    -------
    JtagLink
        A JtagLink with a live-detected hardware_name (see
        jtag.detect_jtag_hardware) and cfg's device_name.
    """
    return JtagLink(
        hardware_name=detect_jtag_hardware(), device_name=cfg["quartus"]["jtag_device"]
    )


def _root(args: argparse.Namespace) -> Path:
    """Resolve the consuming project's root directory for a subcommand.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    Path
        Path(args.root).resolve() if --root was passed, else the
        current working directory.
    """
    return Path(args.root).resolve() if args.root else Path.cwd()


def _discover_tests(root: Path, cfg: dict[str, Any]) -> list[Path]:
    """Find every test source under paths.c_dir/paths.asm_dir.

    Each test is its own <c_dir|asm_dir>/<name>/ folder containing
    exactly one `src.c` or `src.S` and, for "memory"-kind tests, a
    `golden.json` holding the expected {byte address: byte value}
    map (see mem_validator.compare) — kept next to the source instead
    of a separate golden/ directory.

    A folder containing a `.off` file is skipped entirely (with a
    printed note) instead of being built — for a test that's known to
    be permanently unbuildable/inapplicable on this target (e.g. one
    that needs something the hardware genuinely can't do) rather than
    a transient failure. `.off`'s content, if any, is printed as the
    reason; keep it short and point at fuller docs if there's a real
    investigation behind it. This is deliberately not a way to "skip
    a currently-broken test" — a test that should eventually work
    again belongs in version control failing loudly, not silenced.

    Parameters
    ----------
    root : Path
        The consuming project's root directory.
    cfg : dict of {str: Any}
        The merged project config — uses paths.c_dir/paths.asm_dir.

    Returns
    -------
    list of Path
        Every `src.c`/`src.S` found (excluding `.off` folders), sorted
        by test name (the parent folder's name) — folder names must be
        unique across c_dir/asm_dir combined.
    """
    c_dir = root / cfg["paths"]["c_dir"]
    asm_dir = root / cfg["paths"]["asm_dir"]
    sources = list(c_dir.glob("*/src.c")) + list(asm_dir.glob("*/src.S"))

    kept: list[Path] = []
    for src in sources:
        off_marker = src.parent / ".off"
        if off_marker.is_file():
            reason = off_marker.read_text().strip()
            suffix = f": {reason}" if reason else ""
            print(f"Skipping {src.parent.name} (.off present){suffix}")
            continue
        kept.append(src)

    return sorted(kept, key=lambda p: p.parent.name)


def cmd_compile(args: argparse.Namespace) -> None:
    """Implement `riscv-tools compile`.

    Builds every test under paths.c_dir/paths.asm_dir into .mif/.hex
    (+ the combined manifest.json), or into human-readable .s (no
    manifest) for --emit asm. Each test is its own
    <c_dir|asm_dir>/<name>/ folder (see _discover_tests) — "real"
    (--emit mif) builds every test regardless of kind, "sim" (--emit
    hex) skips "memory"-kind tests, since sim doesn't verify RAM
    contents (only the PASS/FAIL mailbox), and building one would
    silently under-verify it instead of catching a wrong computed
    value.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments. Uses args.config, args.root, args.emit
        ("mif", "hex", or "asm"), args.manifest (full path override
        for the combined manifest.json; default
        <build_dir>/manifest.json), args.manifest_per_test (a full
        path template containing "{name}", e.g. "some/dir/{name}.json"
        — if given, ALSO writes each test's own manifest entry to its
        own file, substituting "{name}" with that test's name; the
        combined manifest.json is still written either way, since
        `run` reads it).

    Returns
    -------
    None
        Exits the process with status 1 if no tests are found, or if
        a "memory"-kind test (--emit mif only) is missing its
        manifest.json.
    """
    cfg = load_config(args.config)
    root = _root(args)

    sources = _discover_tests(root, cfg)
    if not sources:
        print(
            f"No tests found under {root / cfg['paths']['c_dir']} or "
            f"{root / cfg['paths']['asm_dir']}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.emit == "asm":
        build_dir = root / cfg["paths"]["build_dir"] / "asm"
        for src in sources:
            asm = c_to_asm_mod.c_to_asm(
                cfg["toolchain"],
                cfg["isa"],
                src,
                src.parent.name,
                build_dir,
                root / cfg["paths"]["include_dir"],
            )
            print(f"Wrote {asm}")
        return

    is_real = args.emit == "mif"
    build_dir = root / cfg["paths"]["build_dir"] / ("real" if is_real else "sim")

    manifest: list[dict[str, Any]] = []

    for src in sources:
        name = src.parent.name

        kind_peek = compiler_mod.parse_header(
            cfg["isa"], cfg["quartus"]["default_timeout_s"], src.read_text()
        )[1]
        if kind_peek == "memory" and not is_real:
            print(f"Skipping {name}: sim doesn't verify memory-kind tests")
            continue

        print(f"Building {src.relative_to(root)} ...")

        bin_, march, kind, timeout_s = compiler_mod.compile_test(
            cfg["toolchain"],
            cfg["isa"],
            cfg["quartus"]["default_timeout_s"],
            src,
            name,
            build_dir,
            root / cfg["paths"]["include_dir"],
            root / cfg["paths"]["crt0"],
            root / cfg["paths"]["linker_script"],
        )

        entry: dict[str, Any] = {"name": name, "march": march, "kind": kind}

        if is_real:
            entry["timeout_s"] = timeout_s
            mif = build_dir / f"{name}.mif"
            bin_to_image.bin_to_mif(bin_, mif, depth=cfg["memory"]["rom_words"])
            entry["mif"] = str(mif.relative_to(root))

            if kind == "memory":
                golden_path = src.parent / "manifest.json"

                if not golden_path.is_file():
                    print(
                        f"ERROR: {name} is memory but {golden_path} is missing",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                entry["golden"] = str(golden_path.relative_to(root))
        else:
            hex_ = build_dir / f"{name}.hex"
            bin_to_image.bin_to_hex(bin_, hex_)
            entry["hex"] = str(hex_.relative_to(root))

        if args.manifest_per_test:
            per_test_path = Path(args.manifest_per_test.format(name=name))
            per_test_path.parent.mkdir(parents=True, exist_ok=True)
            per_test_path.write_text(json.dumps(entry, indent=2))
            print(f"Wrote {per_test_path}")

        manifest.append(entry)

    manifest_path = (
        Path(args.manifest) if args.manifest else build_dir / "manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"Wrote {manifest_path} ({len(manifest)} test(s))")


def cmd_write_rom(args: argparse.Namespace) -> None:
    """Implement `riscv-tools write-rom`.

    JTAG-writes a .mif into the ROM instance of the already-programmed
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
    link = _link(cfg)
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instance"], Path(args.mif))


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
    link = _link(cfg)
    ram_zero.zero_ram(
        link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_words"]
    )


def cmd_dump_ram(args: argparse.Namespace) -> None:
    """Implement `riscv-tools dump-ram`.

    JTAG-saves the whole RAM instance of the already-programmed board
    to a .mif.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.out.

    Returns
    -------
    None
    """
    cfg = load_config(args.config)
    link = _link(cfg)
    ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], Path(args.out))


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
    link = _link(cfg)
    root = _root(args)

    quartus_program.full_reconfigure(
        hardware_name=link.hardware_name,
        project_dir=root / cfg["quartus"]["project_dir"],
        project_name=cfg["quartus"]["project_name"],
        sof_file=cfg["quartus"]["sof_file"],
        rom_mif_target=cfg["quartus"]["rom_mif_target"],
        stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        rom_mif_path=Path(args.mif),
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
    link = _link(cfg)

    if args.action == "read":
        value = mailbox.read_mailbox(
            link,
            cfg["quartus"]["ram_mem_instance"],
            cfg["memory"]["ram_base"],
            cfg["memory"]["mailbox_addr"],
        )
        print(f"MAILBOX={value}")

    else:
        mailbox.pulse_go_flag(
            link,
            cfg["quartus"]["ram_mem_instance"],
            cfg["memory"]["ram_base"],
            cfg["memory"]["go_flag_addr"],
        )


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
    root = _root(args)
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
        (parsed with base 0, so "0x10" or "16" both work) — the
        argument parser enforces exactly one of these two is given.

    Returns
    -------
    None
        Prints the number of bytes written to stdout.
    """
    if bool(args.symbol) == bool(args.start or args.end):
        print(
            "error: pass either --symbol, or both --start and --end (not both forms)",
            file=sys.stderr,
        )
        sys.exit(2)
    if bool(args.start) != bool(args.end):
        print("error: --start and --end must be given together", file=sys.stderr)
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
        spike_bin=cfg["emulator"]["spike_bin"],
        nm_bin=nm_bin,
        elf_path=elf_path,
        isa=args.march,
        tohost_symbol=cfg["emulator"]["tohost_symbol"],
        addr_start=addr_start,
        addr_end=addr_end,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    golden_generator.write_golden_json(golden, out_path)
    print(f"Wrote {out_path} ({len(golden)} bytes)")


def cmd_run(args: argparse.Namespace) -> None:
    """Implement `riscv-tools run`.

    Runs the real-hardware test suite from a manifest.json (see
    orchestrator.run_suite) — the full manifest by default, or a
    caller-picked subset via --only.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root,
        args.manifest (defaults to <build_dir>/real/manifest.json if
        not given), args.only (list of test names to run instead of
        the whole manifest — each entry may itself be a comma-
        separated list; repeat --only to add more), args.
        skip_reconfigure (see orchestrator.run_suite's reconfigure
        param).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if the manifest file is missing, if --only names a
        test that isn't in the manifest, or if any test failed.
    """
    cfg = load_config(args.config)
    root = _root(args)
    build_dir = root / cfg["paths"]["build_dir"] / "real"
    manifest_path = (
        Path(args.manifest) if args.manifest else build_dir / "manifest.json"
    )

    if not manifest_path.is_file():
        print(
            f"{manifest_path} not found — run `riscv-tools compile --emit mif` first",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest: list[dict[str, Any]] = json.loads(manifest_path.read_text())

    if args.only:
        wanted = [name for group in args.only for name in group.split(",") if name]
        by_name = {entry["name"]: entry for entry in manifest}
        missing = [name for name in wanted if name not in by_name]
        if missing:
            print(
                f"--only names not found in {manifest_path}: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(1)
        manifest = [by_name[name] for name in wanted]

    link = _link(cfg)
    print(f"JTAG hardware: {link.hardware_name}")
    project_dir = root / cfg["quartus"]["project_dir"]

    results = orchestrator.run_suite(
        cfg,
        link,
        manifest,
        build_dir,
        root,
        project_dir,
        reconfigure=not args.skip_reconfigure,
    )

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        sys.exit(1)


def cmd_sim(args: argparse.Namespace) -> None:
    """Implement `riscv-tools sim`.

    Runs the full simulation test suite under cocotb/GHDL from a
    manifest.json (see sim_runner.run_suite). Requires the "sim"
    extra (cocotb) to be installed.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root,
        args.manifest (defaults to <build_dir>/sim/manifest.json if
        not given).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if the manifest file is missing, or if any test
        failed.
    """
    cfg = load_config(args.config)
    root = _root(args)
    build_dir = root / cfg["paths"]["build_dir"] / "sim"
    manifest_path = (
        Path(args.manifest) if args.manifest else build_dir / "manifest.json"
    )

    if not manifest_path.is_file():
        print(
            f"{manifest_path} not found — run `riscv-tools compile --emit hex` first",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest: list[dict[str, Any]] = json.loads(manifest_path.read_text())

    results = sim_runner.run_suite(cfg, manifest, root, build_dir / "sim_work")

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        sys.exit(1)


def cmd_vhdl_sort(args: argparse.Namespace) -> None:
    """Implement `riscv-tools vhdl-sort`.

    Prints args.files reordered so each file's VHDL entity/package
    dependencies precede it (see vhdl_sort.topo_sort) — for feeding
    GHDL's `-a` (analyze) phase, or a Makefile's `$(shell ...)`.
    Doesn't touch args.config; this subcommand needs no project
    config.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.files.

    Returns
    -------
    None
        Prints the reordered file paths, space-separated, to stdout.
    """
    ordered = vhdl_sort.topo_sort([Path(f) for f in args.files])
    print(" ".join(str(f) for f in ordered))


def cmd_freq_sweep(args: argparse.Namespace) -> None:
    """Implement `riscv-tools freq-sweep`.

    Finds the board's Fmax for a fixed test program by sweeping (or
    binary-searching) candidate clock frequencies, editing the
    project's PLL and doing a full recompile+reprogram+RAM-compare at
    each one (see orchestrator.run_freq_sweep_linear/
    run_freq_sweep_binary).

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root, args.mif,
        args.golden, args.binary, args.start/args.stop/args.step
        (linear mode), args.low/args.high (binary mode), args.out
        (results JSON path; default
        <build_dir>/freq_sweep/freq_sweep_results.json).

    Returns
    -------
    None
        Writes results to args.out and prints a summary. Exits the
        process with status 1 if no candidate frequency passed.
    """
    cfg = load_config(args.config)
    root = _root(args)
    link = _link(cfg)
    project_dir = root / cfg["quartus"]["project_dir"]
    build_dir = root / cfg["paths"]["build_dir"] / "freq_sweep"
    build_dir.mkdir(parents=True, exist_ok=True)

    mif_path = Path(args.mif)
    golden_path = Path(args.golden)

    if args.binary:
        results = orchestrator.run_freq_sweep_binary(
            cfg,
            link,
            mif_path,
            golden_path,
            project_dir,
            build_dir,
            args.low,
            args.high,
        )
    else:
        results = orchestrator.run_freq_sweep_linear(
            cfg,
            link,
            mif_path,
            golden_path,
            project_dir,
            build_dir,
            args.start,
            args.stop,
            args.step,
        )

    out_path = Path(args.out) if args.out else build_dir / "freq_sweep_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {out_path}")

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['freq_mhz']:>8} MHz : {r['status']}")

    passes = [r["freq_mhz"] for r in results if r["status"] == "pass"]
    if passes:
        print(f"Highest passing frequency: {max(passes)} MHz")
    else:
        print("No candidate frequency passed", file=sys.stderr)
        sys.exit(1)


# Statement count grows with each subcommand's own add_argument calls
# (repetitive parser wiring, not real branching complexity) — splitting
# it up would just move the same lines behind indirection.
def main() -> None:  # noqa: PLR0915
    """CLI entry point (console script `riscv-tools`).

    Builds the argument parser, registers every subcommand, and
    dispatches to its cmd_* handler. Reads sys.argv via argparse; no
    parameters.

    Returns
    -------
    None
        Exits the process with a non-zero status on argument errors,
        or whatever the dispatched cmd_* function causes (see each
        cmd_*'s own Returns/Raises).
    """
    parser = argparse.ArgumentParser(
        prog="riscv-tools",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the consuming project's config.yaml "
        "(required for every subcommand except vhdl-sort)",
    )
    parser.add_argument(
        "--root", default=None, help="Consuming project's root dir (default: cwd)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "compile",
        help="Compile tests/c/{real,sim} into mif/hex/asm (+ manifest.json)",
    )
    p.add_argument("--emit", choices=["mif", "hex", "asm"], required=True)
    p.add_argument(
        "--manifest",
        default=None,
        help="Full path override for the combined manifest.json "
        "(default: <build_dir>/manifest.json)",
    )
    p.add_argument(
        "--manifest-per-test",
        default=None,
        help='Full path template containing "{name}" (e.g. "some/dir/{name}.json") — '
        "if given, also writes each test's own manifest entry to its own file",
    )
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("write-rom", help="JTAG-write a .mif into the ROM instance")
    p.add_argument("mif")
    p.set_defaults(func=cmd_write_rom)

    p = sub.add_parser("zero-ram", help="JTAG-zero the whole RAM instance")
    p.set_defaults(func=cmd_zero_ram)

    p = sub.add_parser("dump-ram", help="JTAG-dump the whole RAM instance to a .mif")
    p.add_argument("out")
    p.set_defaults(func=cmd_dump_ram)

    p = sub.add_parser(
        "program",
        help="Compile the Quartus project and program the board (full reconfigure)",
    )
    p.add_argument(
        "mif", help=".mif to bake in as the ROM's init_file before compiling"
    )
    p.set_defaults(func=cmd_program)

    p = sub.add_parser(
        "mailbox", help="Read the PASS/FAIL mailbox, or pulse the restart go-flag"
    )
    p.add_argument("action", choices=["read", "pulse"])
    p.set_defaults(func=cmd_mailbox)

    p = sub.add_parser(
        "generate-header",
        help="Generate rv32_test.h from config.yaml's memory.mailbox_addr",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Output path (default: <paths.include_dir>/rv32_test.h)",
    )
    p.set_defaults(func=cmd_generate_header)

    p = sub.add_parser(
        "generate-golden",
        help="Generate a golden JSON by running an ELF under Spike",
    )
    p.add_argument("elf")
    p.add_argument("--march", required=True, help="e.g. rv32im")
    p.add_argument(
        "--symbol",
        default=None,
        help="Data symbol to snapshot (e.g. a C global) — its address and size "
        "are resolved automatically via `nm -S`, instead of --start/--end. "
        "Mutually exclusive with --start/--end.",
    )
    p.add_argument(
        "--start", default=None, help="First byte address to snapshot (hex or decimal)"
    )
    p.add_argument(
        "--end",
        default=None,
        help="One past the last byte address to snapshot (hex or decimal)",
    )
    p.add_argument("--out", required=True, help="Where to write the golden .json")
    p.set_defaults(func=cmd_generate_golden)

    p = sub.add_parser(
        "run", help="Run the real-hardware test suite from a manifest.json"
    )
    p.add_argument("--manifest", default=None)
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Only run these test(s) (by manifest name), instead of the whole "
        "suite — repeatable, and/or comma-separated in one use. Implies you "
        "probably also want --skip-reconfigure if the board is already "
        "running a compatible bitstream.",
    )
    p.add_argument(
        "--skip-reconfigure",
        action="store_true",
        help="Skip the initial compile+program step and go straight to "
        "JTAG-loading each test's ROM — only safe if the board is ALREADY "
        "programmed with a compatible bitstream (e.g. re-running a few "
        "tests that failed earlier in the same session). Getting this wrong "
        "looks like every test timing out, not a clean error.",
    )
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "sim",
        help="Run the full simulation test suite (cocotb/GHDL) from a manifest.json",
    )
    p.add_argument("--manifest", default=None)
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser(
        "vhdl-sort",
        help="Print VHDL files in GHDL analyze order (dependencies first)",
    )
    p.add_argument("files", nargs="+", help="VHDL source files to order")
    p.set_defaults(func=cmd_vhdl_sort)

    p = sub.add_parser(
        "freq-sweep",
        help="Sweep/binary-search clock frequency to find Fmax "
        "(edits the PLL + full recompile+reprogram per candidate)",
    )
    p.add_argument(
        "mif",
        help=".mif to bake in as the ROM's init_file at every candidate frequency",
    )
    p.add_argument(
        "--golden",
        required=True,
        help="Golden JSON the post-run RAM dump is compared against",
    )
    p.add_argument(
        "--binary", action="store_true", help="Binary search instead of linear sweep"
    )
    p.add_argument("--start", type=float, default=1.0, help="(linear) start freq, MHz")
    p.add_argument("--stop", type=float, default=30.0, help="(linear) stop freq, MHz")
    p.add_argument("--step", type=float, default=2.0, help="(linear) step, MHz")
    p.add_argument("--low", type=float, default=1.0, help="(binary) low bound, MHz")
    p.add_argument("--high", type=float, default=50.0, help="(binary) high bound, MHz")
    p.add_argument(
        "--out",
        default=None,
        help="Results JSON path "
        "(default: <build_dir>/freq_sweep/freq_sweep_results.json)",
    )
    p.set_defaults(func=cmd_freq_sweep)

    args = parser.parse_args()
    if args.command != "vhdl-sort" and args.config is None:
        parser.error("--config is required for this subcommand")
    args.func(args)


if __name__ == "__main__":
    main()
