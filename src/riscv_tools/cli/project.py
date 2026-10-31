"""Project config helpers, test discovery and golden generation."""

from dataclasses import replace
from pathlib import Path
from typing import Any

from riscv_tools import (
    bin_to_image,
    golden_generator,
)
from riscv_tools import compiler as compiler_mod
from riscv_tools.cli.discovery import CTest
from riscv_tools.cli.toolchain import (
    build_setup,
    optional_path,
    spike_target,
    syscalls_sources,
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
    golden_linker = optional_path(cfg, root, "golden_linker_script")
    boot_rom_src = optional_path(cfg, root, "boot_rom")
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
                    *syscalls_sources(cfg, root),
                ],
                link_flags=list(cfg["emulator"].get("gcc_flags", [])),
            ),
        )
        compiler_mod.compile_test(setup, src, f"{name}.golden", build_dir)
    else:
        elf_path = build_dir / f"{name}.elf"
    return elf_path


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
