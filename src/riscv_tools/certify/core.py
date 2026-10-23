"""Build and run the ACT4 architectural certification suite under cocotb/GHDL.

Two stages, kept separate since they're owned by different tools:

1. `build_elfs` shells out to ACT4's own `make` (vendor/riscv-arch-test)
   to compile self-checking ELFs for this project's own ACT4 target
   (act.target_config in config.yaml — see
   tools/riscv_build/act/rv32im-min/). ACT4 owns test generation/
   compilation entirely; this project only supplies the DUT-specific
   config (test_config.yaml, UDB YAML, rvmodel_macros.h, link.ld).
2. `run_suite` splits each built ELF by address into the images the simulation
   loads (the code region into the instruction memory and the boot ROM, the data
   region into the RAM; every section of an ACT4 ELF is loaded at the address it
   runs from), and drives it through the SAME cocotb/GHDL toplevel
   `sim_runner.run_test` uses for the regular suite, with `test_module` the ACT4
   one: ACT4 tests signal completion via HTIF tohost, not this project's own
   PASS/FAIL mailbox convention (see rv32im-min/rvmodel_macros.h).

Doesn't touch real hardware at all — ACT4 tests have no golden.json/
Spike-comparison step of their own (self-checking: the expected value
is baked into each test's own assembly at generation time, upstream,
long before this project ever sees it), so there's nothing here
analogous to orchestrator.run_suite's real-hardware path.
"""

import resource
import struct
from pathlib import Path
from typing import Any

import yaml

from riscv_tools import bin_to_image, proc, sim_runner

_ACT_TEST_MODULE = "tools.riscv_build.act.sim.test_act"


def _target_name(target_config: Path) -> str:
    """Read an ACT4 test_config.yaml's own `name:` field.

    Parameters
    ----------
    target_config : Path
        Path to the ACT4 target's test_config.yaml.

    Returns
    -------
    str
        The `name:` value — ACT4 builds this config's ELFs into
        `<vendor_dir>/work/<name>/elfs/` (see vendor/riscv-arch-test's
        own Makefile: `WORKDIR/$(config-name)`).
    """
    data = yaml.safe_load(target_config.read_text())
    return str(data["name"])


def build_elfs(
    vendor_dir: Path, target_config: Path, extensions: str, jobs: int
) -> Path:
    """Build this project's ACT4 target's self-checking ELFs via ACT4's own `make`.

    Parameters
    ----------
    vendor_dir : Path
        The vendored, pinned vendor/riscv-arch-test checkout (ACT4
        framework root — has its own top-level Makefile).
    target_config : Path
        This project's own ACT4 target test_config.yaml (act.target_config
        in config.yaml) — passed to `make` as an absolute path, since
        ACT4's own CONFIG_FILES accepts any path, not just ones under
        its own config/ tree (see vendor/riscv-arch-test's README:
        "Configs can also be placed outside the repo").
    extensions : str
        Comma-separated extension list (act.extensions in config.yaml,
        e.g. "I,M") — forwarded as `make`'s own EXTENSIONS=.
    jobs : int
        Forwarded as `make`'s own JOBS= (0 = auto-detect, ACT4's own
        default).

    Returns
    -------
    Path
        `<vendor_dir>/work/<target-name>/elfs` — where the just-built
        ELFs landed.

    Raises
    ------
    subprocess.CalledProcessError
        `make` exited non-zero (e.g. a compile error, or the Ruby/
        Bundler/UDB toolchain ACT4's own Makefile requires isn't
        installed — see certification.yml).
    """
    proc.run_streaming(
        [
            "make",
            f"CONFIG_FILES={target_config.resolve()}",
            f"EXTENSIONS={extensions}",
            f"JOBS={jobs}",
        ],
        cwd=vendor_dir,
    )
    return vendor_dir / "work" / _target_name(target_config) / "elfs"


def discover_elfs(elfs_dir: Path) -> list[Path]:
    """Find every self-checking ELF `build_elfs` produced.

    Parameters
    ----------
    elfs_dir : Path
        `build_elfs`'s own return value.

    Returns
    -------
    list of Path
        Every `*.elf` under elfs_dir, sorted, EXCLUDING `*.sig.elf`
        (a separate signature-mode build ACT4 produces for
        `make coverage`'s Sail-comparison flow — irrelevant here,
        this project only runs the self-checking `.elf` build; see
        certify/core.py's own module docstring).
    """
    return sorted(p for p in elfs_dir.rglob("*.elf") if not p.name.endswith(".sig.elf"))


_PT_LOAD = 1
_ELF32_HEADER = struct.Struct("<16xHHIIIIIHHHHHH")
_ELF32_PHDR = struct.Struct("<IIIIIIII")


def load_segments(elf: Path) -> list[tuple[int, bytes]]:
    """Read the loadable segments of a little-endian 32-bit ELF.

    Parameters
    ----------
    elf : Path
        The ELF file.

    Returns
    -------
    list of (int, bytes)
        The physical address and the file contents of every `PT_LOAD` segment that has
        contents. Segments that only reserve zeroed space (`.bss`, the HTIF
        words) have none.
    """
    data = elf.read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ValueError(f"{elf} is not a little-endian 32-bit ELF")
    fields = _ELF32_HEADER.unpack_from(data)
    phoff, phentsize, phnum = fields[4], fields[8], fields[9]
    segments: list[tuple[int, bytes]] = []
    for index in range(phnum):
        kind, offset, _vaddr, paddr, filesz, _memsz, _flags, _align = (
            _ELF32_PHDR.unpack_from(data, phoff + index * phentsize)
        )
        if kind == _PT_LOAD and filesz:
            segments.append((paddr, data[offset : offset + filesz]))
    return segments


def region_image(segments: list[tuple[int, bytes]], start: int, end: int) -> bytes:
    """Build the flat image of the address range `[start, end)` from the segments.

    Parameters
    ----------
    segments : list of (int, bytes)
        The result of `load_segments`.
    start, end : int
        The first address of the range and the first address past it.

    Returns
    -------
    bytes
        The bytes of the range from `start` to the last byte any segment puts
        there, with zeros between segments; empty if no segment touches the range.
    """
    image = bytearray()
    for address, contents in segments:
        low, high = max(address, start), min(address + len(contents), end)
        if low >= high:
            continue
        if len(image) < high - start:
            image.extend(bytes(high - start - len(image)))
        image[low - start : high - start] = contents[low - address : high - address]
    return bytes(image)


def write_images(
    elf: Path, out_dir: Path, name: str, ram_base: int, boot_bytes: int
) -> dict[str, Path]:
    """Write the three hex images the simulation loads from one ACT4 ELF.

    The ELF has every section loaded at the address it runs from. The code region
    (below `ram_base`) goes to the instruction memory and its first `boot_bytes`
    bytes also to the boot ROM, which the core fetches from below that address;
    the data region (from `ram_base`) goes to the RAM.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF.
    out_dir : Path
        Where the `.bin` and `.hex` files are written.
    name : str
        Stem of the file names.
    ram_base : int
        First address of the RAM.
    boot_bytes : int
        Size in bytes of the boot ROM, at address 0.

    Returns
    -------
    dict of {str: Path}
        The hex files, under the keys `boot_hex_path`, `hex_path` and `ram_hex_path`.
    """
    segments = load_segments(elf)
    code = region_image(segments, 0, ram_base)
    data = region_image(segments, ram_base, 1 << 32)
    images = {
        "boot_hex_path": code[:boot_bytes],
        "hex_path": code,
        "ram_hex_path": data,
    }
    paths: dict[str, Path] = {}
    for key, image in images.items():
        suffix = key.removesuffix("_hex_path") if key != "hex_path" else "rom"
        bin_path = out_dir / f"{name}.{suffix}.bin"
        hex_path = out_dir / f"{name}.{suffix}.hex"
        # at least one word, so that the file is never empty
        bin_path.write_bytes(image or bytes(4))
        bin_to_image.bin_to_hex(bin_path, hex_path)
        paths[key] = hex_path
    return paths


def _raise_stack_limit() -> None:
    """Raise the soft stack limit of this process to the hard one.

    The simulation memories of the ACT4 target are big arrays (millions of
    words), and GHDL allocates them on the stack of the simulation; with the
    default limit it ends with exit code 255 and no message. The simulation
    processes inherit the limit.
    """
    _soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


def run_suite(cfg: dict[str, Any], root: Path, build_dir: Path) -> dict[str, bool]:
    """Build then run every ACT4 ELF for this project's own target under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses act.vendor_dir/target_config/
        extensions/jobs/sim_parameters (optional — merged on top of
        sim.parameters, for a memory-depth generic ACT4's own bigger
        images need but the regular suite doesn't) and sim.toplevel/
        vhdl_sources/ghdl_std/parameters (NOT sim.test_module — see
        module docstring).
    root : Path
        The consuming project's root directory — act.vendor_dir/
        target_config and sim.vhdl_sources are all resolved relative
        to this.
    build_dir : Path
        Where converted `.bin`/`.hex` images and per-test GHDL build
        artifacts go (a subdirectory per ELF, mirroring sim_runner's
        own convention).

    Returns
    -------
    dict of {str: bool}
        A {elf stem: passed} dict, one entry per ELF `build_elfs`
        produced, in sorted order.
    """
    _raise_stack_limit()
    sim_runner.extend_python_path(root, [".", *(cfg["sim"].get("python_path") or [])])
    act_cfg = cfg["act"]
    vendor_dir = root / act_cfg["vendor_dir"]
    target_config = root / act_cfg["target_config"]

    elfs_dir = build_elfs(
        vendor_dir, target_config, act_cfg["extensions"], act_cfg["jobs"]
    )
    elfs = discover_elfs(elfs_dir)
    if not elfs:
        print(f"No ELFs found under {elfs_dir} — nothing to run")
        return {}

    vhdl_sources = [str(root / src) for src in cfg["sim"]["vhdl_sources"]]
    # act.sim_parameters overrides/extends sim.parameters — an official
    # architectural test can be far bigger than anything this project's
    # own hand-picked suite needs (e.g. I-jal-00's combinatorial offset
    # coverage overflows this project's real-hardware-sized ROM by
    # tens of KB), and ACT4 never runs on real hardware at all (see
    # this module's own docstring) — its ROM_simulation/RAM_simulation
    # arrays are plain VHDL arrays with no real M10K budget to respect,
    # so sizing them generously here costs nothing. A project with no
    # such override just gets sim.parameters unchanged.
    parameter_templates: dict[str, Any] = {
        **(cfg["sim"].get("parameters") or {}),
        **(act_cfg.get("sim_parameters") or {}),
    }

    results: dict[str, bool] = {}
    for elf in elfs:
        name = elf.stem
        print(f"\n=== {name} ===")
        test_build_dir = build_dir / name
        test_build_dir.mkdir(parents=True, exist_ok=True)

        images = write_images(
            elf,
            test_build_dir,
            name,
            ram_base=int(str(act_cfg["ram_base"]), 0),
            boot_bytes=int(str(act_cfg["boot_rom_bytes"]), 0),
        )
        hex_path = images["hex_path"]

        parameters: dict[str, Any] = {
            k: v.format(**{key: str(path.resolve()) for key, path in images.items()})
            if isinstance(v, str)
            else v
            for k, v in parameter_templates.items()
        }
        results[name] = sim_runner.run_test(
            toplevel=cfg["sim"]["toplevel"],
            vhdl_sources=vhdl_sources,
            ghdl_std=cfg["sim"]["ghdl_std"],
            test_module=_ACT_TEST_MODULE,
            hex_path=hex_path,
            test_name=name,
            build_dir=test_build_dir / "sim_work",
            parameters=parameters,
            # the memories are big arrays, which GHDL refuses to put on the
            # stack by default
            ghdl_run_flags=["--max-stack-alloc=0"],
        )
        print(f"{name}: {'PASS' if results[name] else 'FAIL'}")

    return results
