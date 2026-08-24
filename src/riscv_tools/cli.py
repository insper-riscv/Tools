#!/usr/bin/env python3
"""Command-line entry point: riscv-tools --config <project's config.yaml> <subcommand> ...

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.)
— this package only ships defaults (see each module's __config__.py
and riscv_tools.settings), never a specific project's values.
"""
import argparse
import json
import sys
from pathlib import Path

from riscv_tools import compiler as compiler_mod
from riscv_tools import mailbox, orchestrator, quartus_program, ram_dump, ram_zero, rom_writer
from riscv_tools.jtag import JtagLink, detect_jtag_hardware
from riscv_tools.settings import load_config


def _link(cfg: dict) -> JtagLink:
    return JtagLink(hardware_name=detect_jtag_hardware(), device_name=cfg["quartus"]["jtag_device"])


def _root(args) -> Path:
    return Path(args.root).resolve() if args.root else Path.cwd()


def cmd_compile(args) -> None:
    cfg = load_config(args.config)
    root = _root(args)
    is_real = args.emit == "mif"
    src_dir = root / (cfg["paths"]["tests_real_dir"] if is_real else cfg["paths"]["tests_sim_dir"])
    build_dir = root / cfg["paths"]["build_dir"] / ("real" if is_real else "sim")

    c_files = sorted(src_dir.glob("*.c")) + sorted(src_dir.glob("*.S"))
    if not c_files:
        print(f"No .c/.S files found in {src_dir}", file=sys.stderr)
        sys.exit(1)

    manifest = []
    for c_file in c_files:
        print(f"Building {c_file.relative_to(root)} ...")
        bin_, march, kind, timeout_s = compiler_mod.compile_test(
            cfg["toolchain"], cfg["isa"], cfg["quartus"]["default_timeout_s"],
            c_file, build_dir,
            root / cfg["paths"]["include_dir"], root / cfg["paths"]["crt0"], root / cfg["paths"]["linker_script"],
        )

        entry = {"name": c_file.stem, "march": march, "kind": kind}
        if is_real:
            entry["timeout_s"] = timeout_s
            mif = build_dir / f"{c_file.stem}.mif"
            compiler_mod.bin_to_mif(bin_, mif, depth=cfg["memory"]["rom_words"])
            entry["mif"] = str(mif.relative_to(root))
            if kind == "integration":
                golden_path = root / cfg["paths"]["golden_dir"] / f"{c_file.stem}.json"
                if not golden_path.is_file():
                    print(f"ERROR: {c_file.name} is integration but {golden_path} is missing", file=sys.stderr)
                    sys.exit(1)
                entry["golden"] = str(golden_path.relative_to(root))
        else:
            hex_ = build_dir / f"{c_file.stem}.hex"
            compiler_mod.bin_to_hex(bin_, hex_)
            entry["hex"] = str(hex_.relative_to(root))

        manifest.append(entry)

    manifest_path = build_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {manifest_path} ({len(manifest)} test(s))")


def cmd_write_rom(args) -> None:
    cfg = load_config(args.config)
    link = _link(cfg)
    rom_writer.write_rom(link, cfg["quartus"]["rom_mem_instance"], Path(args.mif))


def cmd_zero_ram(args) -> None:
    cfg = load_config(args.config)
    link = _link(cfg)
    ram_zero.zero_ram(link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_words"])


def cmd_dump_ram(args) -> None:
    cfg = load_config(args.config)
    link = _link(cfg)
    ram_dump.dump_ram(link, cfg["quartus"]["ram_mem_instance"], Path(args.out))


def cmd_program(args) -> None:
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


def cmd_mailbox(args) -> None:
    cfg = load_config(args.config)
    link = _link(cfg)
    if args.action == "read":
        value = mailbox.read_mailbox(
            link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_base"], cfg["memory"]["mailbox_addr"]
        )
        print(f"MAILBOX={value}")
    else:
        mailbox.pulse_go_flag(
            link, cfg["quartus"]["ram_mem_instance"], cfg["memory"]["ram_base"], cfg["memory"]["go_flag_addr"]
        )


def cmd_run(args) -> None:
    cfg = load_config(args.config)
    root = _root(args)
    build_dir = root / cfg["paths"]["build_dir"] / "real"
    manifest_path = Path(args.manifest) if args.manifest else build_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"{manifest_path} not found — run `riscv-tools compile --emit mif` first", file=sys.stderr)
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text())

    link = _link(cfg)
    print(f"JTAG hardware: {link.hardware_name}")
    project_dir = root / cfg["quartus"]["project_dir"]

    results = orchestrator.run_suite(cfg, link, manifest, build_dir, root, project_dir)

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(results.values()):
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="riscv-tools", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="Path to the consuming project's config.yaml")
    parser.add_argument("--root", default=None, help="Consuming project's root dir (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("compile", help="Compile tests/c/{real,sim} into mif/hex + manifest.json")
    p.add_argument("--emit", choices=["mif", "hex"], required=True)
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("write-rom", help="JTAG-write a .mif into the ROM instance")
    p.add_argument("mif")
    p.set_defaults(func=cmd_write_rom)

    p = sub.add_parser("zero-ram", help="JTAG-zero the whole RAM instance")
    p.set_defaults(func=cmd_zero_ram)

    p = sub.add_parser("dump-ram", help="JTAG-dump the whole RAM instance to a .mif")
    p.add_argument("out")
    p.set_defaults(func=cmd_dump_ram)

    p = sub.add_parser("program", help="Compile the Quartus project and program the board (full reconfigure)")
    p.add_argument("mif", help=".mif to bake in as the ROM's init_file before compiling")
    p.set_defaults(func=cmd_program)

    p = sub.add_parser("mailbox", help="Read the PASS/FAIL mailbox, or pulse the restart go-flag")
    p.add_argument("action", choices=["read", "pulse"])
    p.set_defaults(func=cmd_mailbox)

    p = sub.add_parser("run", help="Run the full real-hardware test suite from a manifest.json")
    p.add_argument("--manifest", default=None)
    p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
