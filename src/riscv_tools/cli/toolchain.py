"""Read the toolchain and build settings from the project config."""

from pathlib import Path
from typing import Any

from riscv_tools.compiler import BuildSetup, LinkSetup
from riscv_tools.spike_exec import SpikeTarget


def _spike_mem_regions(cfg: dict[str, Any]) -> list[tuple[int, int]]:
    """Build the mem_regions of generate_golden from a config.

    The config is the one of the project.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: uses memory.rom_words/ram_base/
        ram_words and, optionally, memory.rom_origin.

    Returns
    -------
    list of (int, int)
        [(rom_origin, rom_bytes), (ram_base, ram_bytes)]; this
        project's real ROM+RAM layout, byte-sized. Spike needs this
        to even load a bare-metal ELF linked to run at/near address 0
        (see generate_golden's own mem_regions doc); ROM and RAM are
        listed as two regions rather than one spanning both, since
        nothing here guarantees they're contiguous for every project
        that uses this package.
    """
    mem = cfg["memory"]
    rom_origin = mem.get("rom_origin") or 0
    return [
        (rom_origin, mem["rom_words"] * 4),
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


def optional_path(cfg: dict[str, Any], root: Path, key: str) -> Path | None:
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


def syscalls_sources(cfg: dict[str, Any], root: Path) -> list[Path]:
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
            crt0=optional_path(cfg, root, "crt0"),
            linker=optional_path(cfg, root, "linker_script"),
            extra_sources=syscalls_sources(cfg, root),
        ),
    )
