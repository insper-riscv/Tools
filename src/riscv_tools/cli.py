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
    boot_rom,
    certify,
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


def _spike_mem_regions(cfg: dict[str, Any]) -> list[tuple[int, int]]:
    """Build golden_generator.generate_golden's mem_regions from a project's config.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses memory.rom_words/ram_base/
        ram_words.

    Returns
    -------
    list of (int, int)
        [(0, rom_bytes), (ram_base, ram_bytes)] — this project's real
        ROM+RAM layout, byte-sized. Spike needs this to even load a
        bare-metal ELF linked to run at/near address 0 (see
        generate_golden's own mem_regions doc) — ROM and RAM are
        listed as two regions rather than one spanning both, since
        nothing here guarantees they're contiguous for every project
        that uses this package.
    """
    mem = cfg["memory"]
    return [
        (0, mem["rom_words"] * 4),
        (mem["ram_base"], mem["ram_words"] * 4),
    ]


def _generate_c_golden(  # noqa: PLR0913, PLR0917
    cfg: dict[str, Any],
    march: str,
    name: str,
    build_dir: Path,
    spike_bin: str | None,
    root: Path,
    src: Path,
) -> tuple[str, Path]:
    """Auto-generate one .c memory test's golden.json by running its ELF under Spike.

    C memory tests never carry a checked-in golden.json — the whole
    point is validating against Spike (the RISC-V Foundation's own
    reference model) fresh every build, not a value someone worked out
    by hand once that can go stale after an edit. Convention: the test
    declares `volatile <type> results[N];` and writes what it wants
    checked there — see docs/creating-a-c-test.md.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    march : str
        This test's own `-march=` string (from compiler.compile_test),
        passed to Spike as `--isa=`.
    name : str
        This test's name — build_dir/{name}.elf must already exist
        (compiler.compile_test's own output), UNLESS
        paths.golden_linker_script is configured (see below), in which
        case a separate build_dir/{name}.golden.elf is built instead.
    build_dir : Path
        Where {name}.elf lives and {name}.golden.json gets written.
    spike_bin : str or None
        Already-resolved `spike` binary path, or None if this is the
        first C memory test in this compile run — resolved once via
        golden_generator.setup() and returned for the caller to reuse
        on subsequent calls, since setup() can be a real build the
        first time Spike isn't already available.
    root : Path
        The consuming project's root directory — resolves
        paths.boot_rom/golden_linker_script.
    src : Path
        This test's own source file (.c) — recompiled against
        paths.golden_linker_script when configured (see below).

    Returns
    -------
    tuple of (str, Path)
        (spike_bin, golden_path) — spike_bin is either the one passed
        in or newly resolved; golden_path is build_dir/{name}.golden.json.
    """
    if spike_bin is None:
        spike_bin = str(golden_generator.setup(cfg["emulator"]["spike_bin"]))

    # A project with a 3-memory BOOT_ROM/FLASH/RAM split (see
    # riscv_tools.boot_rom) can't hand Spike its normal, FLASH-only
    # elf_path: that image has no entry point Spike can run from cold
    # (BOOT_ROM's own gp/sp/.data-copy setup lives in a SEPARATE,
    # unlinked file on real hardware). paths.golden_linker_script
    # (golden.ld in this project) links boot_rom.S + crt0.S + this
    # test's own source together into one self-contained ELF instead,
    # so Spike can start at BOOT_ROM's real entry point
    # (emulator.entry_symbol, e.g. "_reset") the same way real
    # hardware actually boots. A project without that split just
    # keeps reusing build_dir/{name}.elf as before.
    golden_linker = cfg.get("paths", {}).get("golden_linker_script")
    boot_rom_src = cfg.get("paths", {}).get("boot_rom")
    if golden_linker and boot_rom_src:
        elf_path = build_dir / f"{name}.golden.elf"
        compiler_mod.compile_test(
            cfg["toolchain"],
            cfg["isa"],
            0.0,
            src,
            f"{name}.golden",
            build_dir,
            root / cfg["paths"]["include_dir"],
            root / cfg["paths"]["crt0"],
            root / golden_linker,
            extra_sources=[root / boot_rom_src],
        )
    else:
        elf_path = build_dir / f"{name}.elf"

    addr_start, addr_end = golden_generator.symbol_range(
        cfg["toolchain"]["nm"], elf_path, "results"
    )
    golden = golden_generator.generate_golden(
        spike_bin=spike_bin,
        nm_bin=cfg["toolchain"]["nm"],
        elf_path=elf_path,
        isa=march,
        mem_regions=_spike_mem_regions(cfg),
        tohost_symbol=cfg["emulator"]["tohost_symbol"],
        entry_symbol=cfg["emulator"].get("entry_symbol", "_start"),
        addr_start=addr_start,
        addr_end=addr_end,
        ram_base=cfg["memory"]["ram_base"],
    )
    golden_path = build_dir / f"{name}.golden.json"
    golden_generator.write_golden_json(golden, golden_path)
    return spike_bin, golden_path


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


def cmd_compile(args: argparse.Namespace) -> None:  # noqa: PLR0915
    """Implement `riscv-tools compile`.

    Builds every test under paths.c_dir/paths.asm_dir into .mif/.hex
    (+ the combined manifest.json), or into human-readable .s (no
    manifest) for --emit asm. Each test is its own
    <c_dir|asm_dir>/<name>/ folder (see _discover_tests) — "real"
    (--emit mif) builds every test regardless of kind, "sim" (--emit
    hex) skips "memory"-kind .S tests, since sim doesn't verify RAM
    contents (only the PASS/FAIL mailbox) and building one would
    silently under-verify it instead of catching a wrong computed
    value against its checked-in golden.json. "memory"-kind .c tests
    are the exception: their golden.json is generated fresh from Spike
    at real-build time (see _generate_c_golden), not checked in, so
    sim still builds them too — just without any RAM check, same as a
    "unit"-kind test.

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
        golden.json.
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
    # Resolved lazily (once) the first time a .c memory-kind test needs
    # it — most builds never touch a C memory test, and setup() can be
    # a real build (see golden_generator.setup) the first time Spike
    # itself isn't already available.
    spike_bin: str | None = None

    for src in sources:
        name = src.parent.name

        kind_peek = compiler_mod.parse_header(
            cfg["isa"], cfg["quartus"]["default_timeout_s"], src.read_text()
        )[1]
        # .S memory tests carry a checked-in golden.json meant for the
        # real-hardware RAM dump only — building one for sim would
        # silently under-verify it (mailbox PASS regardless of a wrong
        # computed value). .c memory tests are the opposite: their
        # golden.json is generated fresh from Spike at real-build time
        # (see _generate_c_golden) specifically so they don't need one
        # checked in — nothing stops them from also building for sim in
        # a mailbox-only capacity, same as a unit test, keeping them in
        # the fast per-push GHDL suite instead of only ever running on
        # self-hosted real hardware.
        if kind_peek == "memory" and not is_real and src.suffix == ".S":
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

        lang = "C" if src.suffix == ".c" else "ASM"
        entry: dict[str, Any] = {
            "name": name,
            "march": march,
            "kind": kind,
            "lang": lang,
        }

        # FLASH is addressed RAW from BOOT_ROM/FLASH's shared instruction
        # bus (no base-address subtraction in hardware — see
        # rv32im_pipeline_core.vhd), so a test's own image, linked at
        # memory.rom_base, needs that many leading zero words so its
        # real content lands at the matching word index — see
        # bin_to_image.read_words' own docstring for why (a plain
        # `objcopy -O binary` silently drops the leading gap).
        flash_pad_words = cfg["memory"]["rom_base"] // 4

        if is_real:
            entry["timeout_s"] = timeout_s
            mif = build_dir / f"{name}.mif"
            bin_to_image.bin_to_mif(
                bin_,
                mif,
                depth=flash_pad_words + cfg["memory"]["rom_words"],
                pad_words=flash_pad_words,
            )
            entry["mif"] = str(mif.relative_to(root))

            if kind == "memory" and src.suffix == ".c":
                spike_bin, golden_path = _generate_c_golden(
                    cfg, march, name, build_dir, spike_bin, root, src
                )
                entry["golden"] = str(golden_path.relative_to(root))
            elif kind == "memory":
                golden_path = src.parent / "golden.json"

                if not golden_path.is_file():
                    print(
                        f"ERROR: {name} is memory but {golden_path} is missing",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                entry["golden"] = str(golden_path.relative_to(root))
        else:
            hex_ = build_dir / f"{name}.hex"
            bin_to_image.bin_to_hex(bin_, hex_, pad_words=flash_pad_words)
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
    link = _link(cfg)
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instances"], Path(args.mif))


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

    # BOOT_ROM (see riscv_tools.boot_rom) is only ever written here,
    # as part of this full compile — never JTAG-rewritten per test the
    # way FLASH (args.mif) is. Only meaningful for a project with a
    # 3-memory BOOT_ROM/FLASH/RAM split (paths.boot_rom set).
    boot_rom_mif_path = None
    if cfg.get("paths", {}).get("boot_rom") and cfg["quartus"].get("boot_rom_mif_target"):
        build_dir = root / cfg["paths"]["build_dir"] / "boot_rom"
        boot_rom.build_boot_rom(cfg["toolchain"], cfg["paths"], root, build_dir)
        boot_rom_mif_path = build_dir / "boot_rom.mif"
        bin_to_image.bin_to_mif(
            build_dir / "boot_rom.bin",
            boot_rom_mif_path,
            depth=cfg["memory"]["boot_rom_words"],
        )

    quartus_program.full_reconfigure(
        hardware_name=link.hardware_name,
        project_dir=root / cfg["quartus"]["project_dir"],
        project_name=cfg["quartus"]["project_name"],
        sof_file=cfg["quartus"]["sof_file"],
        rom_mif_target=cfg["quartus"]["rom_mif_target"],
        stale_cache_dirs=cfg["quartus"]["stale_cache_dirs"],
        rom_mif_path=Path(args.mif),
        boot_rom_mif_target=cfg["quartus"].get("boot_rom_mif_target"),
        boot_rom_mif_path=boot_rom_mif_path,
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
        spike_bin=str(golden_generator.setup(cfg["emulator"]["spike_bin"])),
        nm_bin=nm_bin,
        elf_path=elf_path,
        isa=args.march,
        mem_regions=_spike_mem_regions(cfg),
        tohost_symbol=cfg["emulator"]["tohost_symbol"],
        addr_start=addr_start,
        addr_end=addr_end,
        ram_base=cfg["memory"]["ram_base"],
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    golden_generator.write_golden_json(golden, out_path)
    print(f"Wrote {out_path} ({len(golden)} bytes)")


def _print_run_summary(
    results: dict[str, bool],
    manifest_by_name: dict[str, dict[str, Any]],
    durations: dict[str, float],
    root: Path,
    build_dir: Path,
) -> None:
    """Print cmd_run's final `PASS/FAIL  name  [lang, kind, golden: ..., Ns]` table."""
    print("\n=== Summary ===")
    name_width = max((len(name) for name in results), default=0)
    for name, ok in results.items():
        entry = manifest_by_name.get(name, {})
        kind = entry.get("kind", "?")
        lang = entry.get("lang", "?")
        detail = f"{lang}, {kind}"
        if kind == "memory" and "golden" in entry:
            # Same test/repo distinction as _generate_c_golden's own
            # ephemeral build/real/<name>.golden.json vs an asm test's
            # checked-in <test_dir>/golden.json — whichever one this
            # test's golden path actually resolves under.
            golden_path = root / entry["golden"]
            origin = "spike" if golden_path.is_relative_to(build_dir) else "checked-in"
            detail = f"{lang}, {kind}, golden: {origin}"
        if name in durations:
            detail = f"{detail}, {durations[name]:.1f}s"
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{name_width}}  [{detail}]")


def cmd_run(args: argparse.Namespace) -> None:
    """Implement `riscv-tools run`.

    Runs the real-hardware test suite from a manifest.json (see
    orchestrator.run_suite) — the full manifest by default, or a
    caller-picked subset via --only. Stops early (doesn't raise) the
    moment a test hits a JTAG/hardware failure no automated retry can
    fix (orchestrator.NeedsHumanInterventionError) — progress is saved
    to <build_dir>/real/run_progress.json as it goes, and simply
    re-running the exact same command later (after fixing the board)
    picks up from where it stopped instead of re-running completed
    tests: this function loads that file itself, if present, and
    narrows the manifest to whatever isn't in it yet.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root,
        args.manifest (defaults to <build_dir>/real/manifest.json if
        not given), args.only (list of test names to run instead of
        the whole manifest — each entry may itself be a comma-
        separated list; repeat --only to add more), args.
        skip_reconfigure (see orchestrator.run_suite's reconfigure
        param), args.wait_for_hardware (see orchestrator.run_suite's
        wait_for_hardware param — off by default, so this still exits
        2 rather than blocking unless explicitly asked to wait),
        args.skip_recompile (see orchestrator.run_suite's
        skip_recompile param).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout when the suite finishes —
        each line also shows the test's source language ("C"/"ASM"),
        kind ("unit"/"memory") and, for memory-kind tests, whether
        their golden.json came from Spike at this same compile (a .c
        test — see cli._generate_c_golden) or is checked into the
        repo (a .S test). Deletes run_progress.json, since there's nothing left
        to resume. Exits the process with status 1 if the manifest file
        is missing, if --only names a test that isn't in the
        manifest, or if any completed test failed; status 2 if the
        suite stopped early for human intervention (run_progress.json
        is left in place in that case, specifically so a re-run finds
        it).
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
    # Kept separate from `manifest` itself, which gets filtered down
    # below (by --only, then again by whatever's already in
    # results_so_far) — the summary at the end still needs every
    # requested test's own kind/golden info, including ones this
    # particular invocation never touched.
    manifest_by_name = {entry["name"]: entry for entry in manifest}

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

    requested_names = {entry["name"] for entry in manifest}
    results_path = build_dir / "run_progress.json"
    results_so_far: dict[str, bool] = {}
    if results_path.is_file():
        results_so_far = {
            name: ok
            for name, ok in json.loads(results_path.read_text()).items()
            if name in requested_names
        }
        if results_so_far:
            print(
                f"Resuming from {results_path} — {len(results_so_far)} "
                f"already-completed test(s) will be skipped"
            )
            manifest = [e for e in manifest if e["name"] not in results_so_far]

    link = _link(cfg)
    print(f"JTAG hardware: {link.hardware_name}")
    project_dir = root / cfg["quartus"]["project_dir"]

    durations: dict[str, float] = {}
    if not manifest:
        # Every requested test was already in results_so_far.
        results = results_so_far
    else:
        results = orchestrator.run_suite(
            cfg,
            link,
            manifest,
            build_dir,
            root,
            project_dir,
            reconfigure=not args.skip_reconfigure,
            results_path=results_path,
            results_so_far=results_so_far,
            wait_for_hardware=args.wait_for_hardware,
            durations=durations,
            skip_recompile=args.skip_recompile,
        )

    _print_run_summary(results, manifest_by_name, durations, root, build_dir)

    if len(results) < len(requested_names):
        print(
            f"\nStopped early: {len(results)}/{len(requested_names)} test(s) "
            f"done. Re-run this exact command after fixing the board to resume."
        )
        sys.exit(2)

    results_path.unlink(missing_ok=True)
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

    # Built ONCE per invocation, reused across every manifest entry --
    # see boot_rom.build_boot_rom / sim_runner.run_suite's own
    # boot_rom_hex_path parameter. Only meaningful for a project whose
    # sim toplevel actually has a BOOT_ROM/FLASH split (paths.boot_rom
    # set) -- skipped otherwise.
    boot_rom_hex_path = None
    if cfg.get("paths", {}).get("boot_rom"):
        boot_rom_hex_path = boot_rom.build_boot_rom(
            cfg["toolchain"], cfg["paths"], root, build_dir / "boot_rom"
        )

    results = sim_runner.run_suite(
        cfg, manifest, root, build_dir / "sim_work", boot_rom_hex_path=boot_rom_hex_path
    )

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        sys.exit(1)


def cmd_certify(args: argparse.Namespace) -> None:
    """Implement `riscv-tools certify`.

    Builds this project's own ACT4 target's self-checking ELFs (see
    act.target_config in config.yaml, and
    tools/riscv_build/act/rv32im-min/) via ACT4's own `make`
    (act.vendor_dir — a pinned vendor/riscv-arch-test submodule), then
    runs each one under cocotb/GHDL (see certify.run_suite). Requires
    the "sim" extra (cocotb), a RISC-V GCC toolchain (compile_exe in
    the ACT4 target's own test_config.yaml), and ACT4's own Ruby/
    Bundler/UDB toolchain (see vendor/riscv-arch-test/README.md
    "Prerequisites") — none of the real-hardware/JTAG toolchain this
    project's other subcommands need.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments — uses args.config, args.root,
        args.extensions (overrides config.yaml's act.extensions when
        given).

    Returns
    -------
    None
        Prints a PASS/FAIL summary to stdout. Exits the process with
        status 1 if any test failed (or if no ELFs were produced at
        all — see certify.run_suite).
    """
    cfg = load_config(args.config)
    if args.extensions is not None:
        cfg["act"]["extensions"] = args.extensions
    root = _root(args)
    build_dir = root / cfg["paths"]["build_dir"] / "act"

    results = certify.run_suite(cfg, root, build_dir)

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not results or not all(results.values()):
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
    p.add_argument(
        "--wait-for-hardware",
        action="store_true",
        help="On a hardware failure that would normally stop the suite "
        "(see NeedsHumanInterventionError), stay running instead of "
        "exiting: print the same message, poll `jtagconfig` every few "
        "seconds until the chain reports healthy again (e.g. after you "
        "physically power-cycle the board), then automatically resume "
        "from the exact step that failed — no need to re-invoke this "
        "command by hand. Meant for an interactive local session someone "
        "is actively watching; CI should keep the default "
        "stop-and-exit-2 behavior instead, since nothing there could "
        "power-cycle the board on its own anyway.",
    )
    p.add_argument(
        "--skip-recompile",
        action="store_true",
        help="On the initial reconfigure step, reprogram from the "
        "already-built .sof (quartus_pgm only, ~10s) instead of doing a "
        "full quartus_sh --flow compile first — only safe if the VHDL "
        "source hasn't changed since that .sof was built (e.g. the "
        "board just lost its configuration to a power-cycle, not a "
        "source edit). Repeated full recompiles in one session have "
        "been observed to destabilize the JTAG chain, so prefer this "
        "over a full reconfigure when you know the .sof is still "
        "current. Unlike --skip-reconfigure, this still reprograms the "
        "board — only the compile step is skipped.",
    )
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "sim",
        help="Run the full simulation test suite (cocotb/GHDL) from a manifest.json",
    )
    p.add_argument("--manifest", default=None)
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser(
        "certify",
        help="Build+run the ACT4 architectural certification suite "
        "(cocotb/GHDL) for this project's own ACT4 target",
    )
    p.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated extension list forwarded to ACT4's own "
        "`make ... EXTENSIONS=` (default: config.yaml's act.extensions)",
    )
    p.set_defaults(func=cmd_certify)

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
