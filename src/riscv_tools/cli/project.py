"""Project config helpers, test discovery and golden generation."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    golden_generator,
)
from riscv_tools import compiler as compiler_mod
from riscv_tools.compiler import BuildSetup, LinkSetup
from riscv_tools.spike_exec import SpikeTarget


def _spike_mem_regions(cfg: dict[str, Any]) -> list[tuple[int, int]]:
    """Build the mem_regions of generate_golden from a config.

    The config is the one of the project.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: uses memory.rom_words/ram_base/
        ram_words.

    Returns
    -------
    list of (int, int)
        [(0, rom_bytes), (ram_base, ram_bytes)]; this project's real
        ROM+RAM layout, byte-sized. Spike needs this to even load a
        bare-metal ELF linked to run at/near address 0 (see
        generate_golden's own mem_regions doc); ROM and RAM are
        listed as two regions rather than one spanning both, since
        nothing here guarantees they're contiguous for every project
        that uses this package.
    """
    mem = cfg["memory"]
    return [
        (0, mem["rom_words"] * 4),
        (mem["ram_base"], mem["ram_words"] * 4),
    ]


def spike_target(
    cfg: dict[str, Any], isa: str, entry_symbol: str = "_start"
) -> SpikeTarget:
    """Build the Spike run settings of a project.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    isa : str
        The `--isa=` value, which should match the test's own march.
    entry_symbol : str, optional
        The symbol execution starts at. Defaults to `_start`.

    Returns
    -------
    SpikeTarget
        The binaries, ISA, memory regions and symbols of the run.
    """
    return SpikeTarget(
        spike_bin=cfg["emulator"]["spike_bin"],
        nm_bin=cfg["toolchain"]["nm"],
        isa=isa,
        mem_regions=_spike_mem_regions(cfg),
        tohost_symbol=cfg["emulator"]["tohost_symbol"],
        entry_symbol=entry_symbol,
        objcopy_bin=cfg["toolchain"]["objcopy"],
    )


def _toolchain_cfg(cfg: dict[str, Any], root: Path) -> dict[str, Any]:
    """Return the `toolchain:` section with `specs` resolved.

    The specs are resolved against the project root.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.

    Returns
    -------
    dict of {str: Any}
        A copy of `cfg["toolchain"]` whose `specs` (when set) is an
        absolute path, so gcc finds it from any working directory.
    """
    toolchain = dict(cfg["toolchain"])
    if toolchain.get("specs"):
        toolchain["specs"] = str((root / toolchain["specs"]).resolve())
    return toolchain


def _optional_path(cfg: dict[str, Any], root: Path, key: str) -> Path | None:
    """Resolve an optional `paths.<key>` against the project root.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.
    key : str
        The key under `paths:` (e.g. "crt0", "linker_script").

    Returns
    -------
    Path or None
        `root / paths.<key>`, or None when the key is not set.
    """
    value = cfg.get("paths", {}).get(key)
    return root / value if value else None


def _syscalls_sources(cfg: dict[str, Any], root: Path) -> list[Path]:
    """Resolve the platform sources every test is compiled with.

    These are `paths.sources` (the platform's own parts of the runtime,
    for instance `_exit`) and the optional `paths.syscalls`, a
    self-contained implementation (for example of malloc()) for projects
    that link with libc "none" (-nostdlib). A project that needs neither
    omits them, and this returns an empty list.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.

    Returns
    -------
    list of Path
        The `paths.sources` entries, then `paths.syscalls` if set, each
        under the project root, meant to be spliced into a compile_test
        call's extra_sources.
    """
    paths = cfg.get("paths", {})
    syscalls = paths.get("syscalls")
    return [
        *[root / source for source in paths.get("sources", [])],
        *([root / syscalls] if syscalls else []),
    ]


def build_setup(cfg: dict[str, Any], root: Path) -> BuildSetup:
    """Build the compile settings shared by every test of a project.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    root : Path
        The consuming project's root directory.

    Returns
    -------
    BuildSetup
        The toolchain, ISA, include directory, crt0, linker script and
        platform sources of the project.
    """
    return BuildSetup(
        toolchain_cfg=_toolchain_cfg(cfg, root),
        isa_cfg=cfg["isa"],
        default_timeout_s=cfg["quartus"]["default_timeout_s"],
        include_dir=root / cfg["paths"]["include_dir"],
        link=LinkSetup(
            crt0=_optional_path(cfg, root, "crt0"),
            linker=_optional_path(cfg, root, "linker_script"),
            extra_sources=_syscalls_sources(cfg, root),
        ),
    )


def spike_elf(
    cfg: dict[str, Any], name: str, build_dir: Path, root: Path, src: Path
) -> Path:
    """Return the ELF Spike should run for one test.

    The ELF is built if needed.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    name : str
        This test's name; build_dir/{name}.elf must already exist
        (compiler.compile_test's own output), unless
        paths.golden_linker_script is configured, in which case a
        separate build_dir/{name}.golden.elf is built instead.
    build_dir : Path
        Where the ELFs live.
    root : Path
        The consuming project's root directory; resolves
        paths.boot_rom/golden_linker_script.
    src : Path
        This test's own source file, recompiled against
        paths.golden_linker_script when configured.

    Returns
    -------
    Path
        The ELF to hand to Spike.
    """
    # A project with a BOOT_ROM/FLASH/RAM split (see
    # riscv_tools.boot_rom) can't always hand Spike its normal,
    # FLASH-only elf_path: on real
    # hardware the boot ROM is a SEPARATE image, so that ELF has nothing
    # at the address the program jumps to when it finishes
    # (rv32_wait_restart, the code that signals HTIF).
    #
    # - emulator.sources: a stand-in for that code (and the tohost/
    #   fromhost symbols), linked into an ELF built just for Spike, with
    #   emulator.gcc_flags. No linker script of the project's: the
    #   toolchain's does the linking (see toolchain.specs).
    # - paths.golden_linker_script (legacy): the test linked together
    # with
    #   the boot ROM source (paths.boot_rom) by the project's own
    #   script, and Spike starts at the boot ROM's entry
    #   (emulator.entry_symbol).
    # - Neither: reuse build_dir/{name}.elf.
    golden_linker = _optional_path(cfg, root, "golden_linker_script")
    boot_rom_src = _optional_path(cfg, root, "boot_rom")
    spike_sources = [root / s for s in cfg["emulator"].get("sources", [])]
    legacy_combined = golden_linker is not None and boot_rom_src is not None
    if spike_sources or legacy_combined:
        elf_path = build_dir / f"{name}.golden.elf"
        base = build_setup(cfg, root)
        setup = replace(
            base,
            default_timeout_s=0.0,
            link=replace(
                base.link,
                linker=golden_linker,
                extra_sources=[
                    *(
                        [boot_rom_src]
                        if legacy_combined and boot_rom_src
                        else []
                    ),
                    *spike_sources,
                    *_syscalls_sources(cfg, root),
                ],
                link_flags=list(cfg["emulator"].get("gcc_flags", [])),
            ),
        )
        compiler_mod.compile_test(setup, src, f"{name}.golden", build_dir)
    else:
        elf_path = build_dir / f"{name}.elf"
    return elf_path


@dataclass(frozen=True)
class CTest:
    """The identity of one C test.

    Parameters
    ----------
    name : str
        This test's name.
    march : str
        This test's own `-march=` string (from compiler.compile_test).
    src : Path
        This test's own source file (.c).
    """

    name: str
    march: str
    src: Path


def generate_c_golden(
    cfg: dict[str, Any], test: CTest, build_dir: Path, root: Path
) -> Path:
    """Generate the golden.json of one .c memory test by running it.

    The test's ELF runs under Spike, so the golden always comes from the
    reference model and never from a hand-written value. The test
    declares `volatile <type> results[N];` and writes there what it
    wants checked.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    test : CTest
        The test. Its march is passed to Spike as `--isa=`.
        build_dir/{name}.elf must exist, unless
        paths.golden_linker_script is set; then
        build_dir/{name}.golden.elf is built from the source against
        that script.
    build_dir : Path
        Where {name}.elf lives and {name}.golden.json gets written.
    root : Path
        The consuming project's root directory, resolves
        paths.boot_rom/golden_linker_script.

    Returns
    -------
    Path
        build_dir/{name}.golden.json.
    """
    name = test.name
    elf_path = spike_elf(cfg, name, build_dir, root, test.src)

    addr_start, addr_end = golden_generator.symbol_range(
        cfg["toolchain"]["nm"], elf_path, "results"
    )
    golden = golden_generator.generate_golden(
        spike_target(
            cfg, test.march, cfg["emulator"].get("entry_symbol", "_start")
        ),
        elf_path,
        (addr_start, addr_end),
        ram_base=cfg["memory"]["ram_base"],
        timeout_s=cfg["emulator"]["timeout_s"],
    )
    golden_path = build_dir / f"{name}.golden.json"
    golden_generator.write_golden_json(golden, golden_path)
    return golden_path


def discover_tests(root: Path, cfg: dict[str, Any]) -> list[Path]:
    """Find every test source under paths.c_dir/paths.asm_dir.

    Each test is a <c_dir|asm_dir>/<name>/ folder with exactly one
    `src.c` or `src.S` and, for "memory"-kind tests, a `golden.json`
    with the expected {byte address: byte value} map.

    A folder with a `.off` file is skipped, and the file's content is
    printed as the reason. Use it for a test that can never build or run
    on this target, not to silence a test that should work.

    Parameters
    ----------
    root : Path
        The consuming project's root directory.
    cfg : dict of {str: Any}
        The merged project config: uses paths.c_dir/paths.asm_dir.

    Returns
    -------
    list of Path
        Every `src.c`/`src.S` found (excluding `.off` folders), sorted
        by test name (the parent folder's name); folder names must be
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


def write_sim_hex(
    cfg: dict[str, Any], stem: Path, bin_: Path, hex_: Path, pad_words: int
) -> None:
    """Write the simulation .hex of a test.

    The format is the one that sim.hex_format selects.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    stem : Path
        The test's build path without extension; `<stem>.elf` is the
        ELF used for the "verilog" format.
    bin_ : Path
        The flat binary used for the "words" format.
    hex_ : Path
        Where to write the .hex.
    pad_words : int
        Leading zero words for the "words" format (see
        bin_to_image.read_words); the "verilog" format carries real
        addresses instead.

    Returns
    -------
    None
    """
    if cfg["sim"]["hex_format"] == "verilog":
        compiler_mod.elf_to_verilog_hex(
            cfg["toolchain"], stem.with_suffix(".elf"), hex_
        )
    else:
        bin_to_image.bin_to_hex(bin_, hex_, pad_words=pad_words)
