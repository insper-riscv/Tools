"""The `compile` subcommand."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
)
from riscv_tools import c_to_asm as c_to_asm_mod
from riscv_tools import compiler as compiler_mod
from riscv_tools.cli.common import project_root
from riscv_tools.cli.discovery import CTest, discover_tests
from riscv_tools.cli.project import generate_c_golden, write_sim_hex
from riscv_tools.cli.test_names import split_test_name_groups
from riscv_tools.cli.toolchain import build_setup
from riscv_tools.settings import load_config


def cmd_compile(args: argparse.Namespace) -> None:
    """Implement `riscv-tools compile`.

    Builds every test under paths.c_dir/paths.asm_dir into .mif/.hex
    plus the combined manifest.json, or into readable .s files (no
    manifest) for --emit asm. Both "real" (--emit mif) and "sim" (--emit
    hex) build every test and attach a "memory"-kind test's golden.json
    to its manifest entry, so the simulation checks the final RAM
    against the golden like the board run does.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed `compile` options: config, root, emit ("mif", "hex" or
        "asm"), manifest (path of the combined manifest.json, default
        <build_dir>/manifest.json), manifest_per_test (path template
        with "{name}"; also writes one manifest per test) and the
        optional only (repeatable, comma-separated test names; builds
        just those tests, so the manifest lists only them).

    Returns
    -------
    None
        Exits the process with status 1 if no tests are found, if
        --only names a test that does not exist, or if a "memory"-kind
        .S test is missing its checked-in golden.json.
    """
    cfg = load_config(args.config)
    root = project_root(args)

    sources = discover_tests(root, cfg)
    if not sources:
        print(
            f"No tests found under {root / cfg['paths']['c_dir']} or "
            f"{root / cfg['paths']['asm_dir']}",
            file=sys.stderr,
        )
        sys.exit(1)
    sources = _select_sources(sources, getattr(args, "only", None))

    if args.emit == "asm":
        _compile_asm(cfg, root, sources)
        return

    is_real = args.emit == "mif"
    build_dir = (
        root / cfg["paths"]["build_dir"] / ("real" if is_real else "sim")
    )

    manifest = [
        _compile_one(args, cfg, root, src, build_dir) for src in sources
    ]

    manifest_path = (
        Path(args.manifest) if args.manifest else build_dir / "manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {manifest_path} ({len(manifest)} test(s))")


def _select_sources(sources: list[Path], only: list[str] | None) -> list[Path]:
    """Keep the sources of the tests `--only` asks for.

    Parameters
    ----------
    sources : list of Path
        Every discovered test source.
    only : list of str, optional
        The repeatable, comma-separated values of `--only`.

    Returns
    -------
    list of Path
        All the sources if `only` is not given, otherwise the named
        ones in the order given. Exits the process with status 1 if
        `--only` is empty or names a test that was not discovered.
    """
    if only is None:
        return sources
    names = split_test_name_groups(only)
    by_name = {src.parent.name: src for src in sources}
    missing = [name for name in names if name not in by_name]
    if not names or missing:
        print(
            "--only needs existing tests"
            + (f", not found: {', '.join(missing)}" if missing else ""),
            file=sys.stderr,
        )
        sys.exit(1)
    return [by_name[name] for name in names]


def _compile_asm(cfg: dict[str, Any], root: Path, sources: list[Path]) -> None:
    """Write the human-readable .s of every test (`--emit asm`).

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.
    sources : list of Path
        The test sources.
    """
    build_dir = root / cfg["paths"]["build_dir"] / "asm"
    for src in sources:
        asm = c_to_asm_mod.c_to_asm(
            cfg["toolchain"],
            cfg["isa"],
            src,
            build_dir / f"{src.parent.name}.s",
            root / cfg["paths"]["include_dir"],
        )
        print(f"Wrote {asm}")


def _compile_one(
    args: argparse.Namespace,
    cfg: dict[str, Any],
    root: Path,
    src: Path,
    build_dir: Path,
) -> dict[str, Any]:
    """Build one test and describe it as a manifest entry.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments; uses args.emit ("mif" or "hex") and
        args.manifest_per_test.
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.
    src : Path
        The test source.
    build_dir : Path
        Where the outputs are written.

    Returns
    -------
    dict of {str: Any}
        The manifest entry of the test.
    """
    name = src.parent.name
    is_real = args.emit == "mif"

    print(f"Building {src.relative_to(root)} ...")

    bin_, march, kind, timeout_s = compiler_mod.compile_test(
        build_setup(cfg, root), src, name, build_dir
    )

    entry: dict[str, Any] = {
        "name": name,
        "march": march,
        "kind": kind,
        "lang": "C" if src.suffix == ".c" else "ASM",
    }
    if is_real:
        entry["timeout_s"] = timeout_s
    _attach_image(entry, cfg, root, (build_dir, bin_), is_real)

    # Attached the same way for "real" and "sim": sim_runner's own
    # cocotb testbench does a bus-snooped RAM-vs-golden compare
    # exactly like orchestrator.run_one's JTAG-dump-vs-golden
    # compare does for real hardware, so a wrong computed value
    # surfaces in simulation.
    if kind == "memory":
        golden_path = _golden_for(cfg, root, build_dir, src, march)
        entry["golden"] = str(golden_path.relative_to(root))

    if args.manifest_per_test:
        per_test_path = Path(args.manifest_per_test.format(name=name))
        per_test_path.parent.mkdir(parents=True, exist_ok=True)
        per_test_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
        print(f"Wrote {per_test_path}")

    return entry


def _attach_image(
    entry: dict[str, Any],
    cfg: dict[str, Any],
    root: Path,
    built: tuple[Path, Path],
    is_real: bool,
) -> None:
    """Convert a test's binary to its .mif/.hex and record the path.

    The FLASH is addressed raw, without base-address subtraction, so an
    image linked at memory.rom_base gets that many leading zero words
    and its content lands at the right word index. With
    memory.rom_origin (the address the first word of the FLASH storage
    has, 0 by default) the padding counts from there: a FLASH behind
    the caches starts at its own base and has none.

    Parameters
    ----------
    entry : dict of {str: Any}
        The manifest entry, which gets its "mif" or "hex" key.
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.
    built : tuple of (Path, Path)
        The build directory and the test's flat binary.
    is_real : bool
        True for a .mif, False for a .hex.
    """
    build_dir, bin_ = built
    name = entry["name"]
    flash_pad_words = (
        cfg["memory"]["rom_base"] - (cfg["memory"].get("rom_origin") or 0)
    ) // 4
    if is_real:
        mif = build_dir / f"{name}.mif"
        bin_to_image.bin_to_mif(
            bin_,
            mif,
            depth=flash_pad_words + cfg["memory"]["rom_words"],
            pad_words=flash_pad_words,
        )
        entry["mif"] = str(mif.relative_to(root))
        return
    hex_ = build_dir / f"{name}.hex"
    write_sim_hex(cfg, build_dir / name, bin_, hex_, flash_pad_words)
    entry["hex"] = str(hex_.relative_to(root))


def _golden_for(
    cfg: dict[str, Any], root: Path, build_dir: Path, src: Path, march: str
) -> Path:
    """Find or generate the golden.json of a "memory" test.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.
    build_dir : Path
        Where the outputs are written.
    src : Path
        The test source.
    march : str
        The `-march=` string of the test.

    Returns
    -------
    Path
        The golden: generated for a .c test, checked in for a .S test.
        Exits the process with status 1 if the latter is missing.
    """
    name = src.parent.name
    if src.suffix == ".c":
        test = CTest(name=name, march=march, src=src)
        return generate_c_golden(cfg, test, build_dir, root)
    golden_path = src.parent / "golden.json"
    if not golden_path.is_file():
        print(
            f"ERROR: {name} is memory but {golden_path} is missing",
            file=sys.stderr,
        )
        sys.exit(1)
    return golden_path
