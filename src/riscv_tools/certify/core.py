"""Build and run the ACT4 certification suite under cocotb/GHDL.

Two stages:

1. `build_elfs` runs ACT4's own `make` to compile the self-checking
   ELFs of this project's ACT4 target (act.target_config).
2. `run_suite` splits each ELF by address into the images the
   simulation loads (code into the instruction memory and the boot ROM,
   data into the RAM) and runs it on the same cocotb/GHDL toplevel as
   the regular suite. ACT4 tests signal completion through HTIF tohost,
   not through the PASS/FAIL mailbox.

No hardware is involved, and there is no golden: each test checks
itself.
"""

import resource
import struct
from pathlib import Path
from typing import Any

import yaml

from riscv_tools import bin_to_image, proc, sim_runner

_ACT_TEST_MODULE = "tools.riscv_build.act.sim.test_act"
_ACT_SDRAM_TEST_MODULE = "tools.riscv_build.act.sim.test_act_sdram"
_ELF_MAGIC = b"\x7fELF"
_PT_LOAD = 1
_ELF32_HEADER = struct.Struct("<16xHHIIIIIHHHHHH")
_ELF32_PHDR = struct.Struct("<IIIIIIII")
_ADDRESS_SPACE = 1 << 32
_NOP = 0x00000013
_LUI_OPCODE = 0x37
_JALR_OPCODE = 0x67
_LOW_12_BITS = 0xFFF
_HIGH_20_BITS = 0xFFFFF000


def target_name(target_config: Path) -> str:
    """Read an ACT4 test_config.yaml's own `name:` field.

    Parameters
    ----------
    target_config : Path
        Path to the ACT4 target's test_config.yaml.

    Returns
    -------
    str
        The `name:` value; ACT4 builds this config's ELFs into
        `<vendor_dir>/work/<name>/elfs/` (see vendor/riscv-arch-test's
        own Makefile: `WORKDIR/$(config-name)`).
    """
    data = yaml.safe_load(target_config.read_text())
    return str(data["name"])


def build_elfs(
    vendor_dir: Path, target_config: Path, extensions: str, jobs: int
) -> Path:
    """Build the self-checking ELFs of this project's ACT4 target.

    Parameters
    ----------
    vendor_dir : Path
        The vendored, pinned vendor/riscv-arch-test checkout (ACT4
        framework root, has its own top-level Makefile).
    target_config : Path
        This project's ACT4 target test_config.yaml (act.target_config
        in config.yaml), passed to `make` as an absolute path.
    extensions : str
        Comma-separated extension list (act.extensions in config.yaml,
        e.g. "I,M"), forwarded as `make`'s own EXTENSIONS=.
    jobs : int
        Forwarded as `make`'s own JOBS= (0 = auto-detect, ACT4's own
        default).

    Returns
    -------
    Path
        `<vendor_dir>/work/<target-name>/elfs`, where the just-built
        ELFs landed.

    Raises
    ------
    subprocess.CalledProcessError
        `make` exited non-zero (e.g. a compile error, or the Ruby/
        Bundler/UDB toolchain ACT4's own Makefile requires isn't
        installed; see certification.yml).
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
    return vendor_dir / "work" / target_name(target_config) / "elfs"


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
        `make coverage`'s Sail-comparison flow, irrelevant here,
        this project only runs the self-checking `.elf` build; see
        certify/core.py's own module docstring).
    """
    return sorted(
        p for p in elfs_dir.rglob("*.elf") if not p.name.endswith(".sig.elf")
    )


def load_segments(elf: Path) -> list[tuple[int, bytes]]:
    """Read the loadable segments of a little-endian 32-bit ELF.

    Parameters
    ----------
    elf : Path
        The ELF file.

    Returns
    -------
    list of (int, bytes)
        The physical address and the file contents of every `PT_LOAD`
        segment that has contents. Segments that only reserve zeroed
        space (`.bss`, the HTIF words) have none.
    """
    data = elf.read_bytes()
    if data[:4] != _ELF_MAGIC or data[4] != 1 or data[5] != 1:
        raise ValueError(f"{elf} is not a little-endian 32-bit ELF")
    fields = _ELF32_HEADER.unpack_from(data)
    phoff, phentsize, phnum = fields[4], fields[8], fields[9]
    segments: list[tuple[int, bytes]] = []
    for index in range(phnum):
        phdr = _ELF32_PHDR.unpack_from(data, phoff + index * phentsize)
        kind, offset, paddr, filesz = phdr[0], phdr[1], phdr[3], phdr[4]
        if kind == _PT_LOAD and filesz:
            segments.append((paddr, data[offset : offset + filesz]))
    return segments


def region_image(
    segments: list[tuple[int, bytes]], start: int, end: int
) -> bytes:
    """Build the flat image of the range `[start, end)` from segments.

    Parameters
    ----------
    segments : list of (int, bytes)
        The result of `load_segments`.
    start, end : int
        The first address of the range and the first address past it.

    Returns
    -------
    bytes
        The bytes of the range from `start` to the last byte any segment
        puts there, with zeros between segments; empty if no segment
        touches the range.
    """
    image = bytearray()
    for address, contents in segments:
        low, high = max(address, start), min(address + len(contents), end)
        if low >= high:
            continue
        if len(image) < high - start:
            image.extend(bytes(high - start - len(image)))
        image[low - start : high - start] = contents[
            low - address : high - address
        ]
    return bytes(image)


def write_images(
    elf: Path, out_dir: Path, name: str, ram_base: int, boot_bytes: int
) -> dict[str, Path]:
    """Write the three hex images the simulation loads from an ELF.

    The code region (below `ram_base`) goes to the instruction memory
    and its first `boot_bytes` bytes also to the boot ROM; the data
    region (from `ram_base`) goes to the RAM. Every section of the ELF
    is loaded at the address it runs from.

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
        The hex files, under the keys `boot_hex_path`, `hex_path` and
        `ram_hex_path`.
    """
    segments = load_segments(elf)
    code = region_image(segments, 0, ram_base)
    data = region_image(segments, ram_base, _ADDRESS_SPACE)
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


def sdram_boot_words(sdram_base: int) -> list[int]:
    """Return the boot ROM that jumps to the SDRAM.

    The words are a nop, `lui x1, base` and `jalr x0, 0(x1)`. The core
    does not execute the first word after the reset, and the base has
    the low 12 bits clear (the SDRAM is 64 MB aligned).
    """
    if sdram_base & _LOW_12_BITS:
        raise ValueError(
            f"the SDRAM base {sdram_base:#x} is not 4 KiB aligned"
        )
    lui_x1 = (sdram_base & _HIGH_20_BITS) | (1 << 7) | _LUI_OPCODE
    jalr_x0 = (1 << 15) | _JALR_OPCODE
    return [_NOP, lui_x1, jalr_x0]


def write_sdram_images(
    elf: Path, out_dir: Path, name: str, sdram_base: int
) -> dict[str, Path]:
    """Write the two hex images the SDRAM simulation loads from an ELF.

    The ELF has everything in the SDRAM, loaded at the address it runs
    from. The image of the SDRAM chip starts at `sdram_base`; the boot
    ROM only jumps there.

    Parameters
    ----------
    elf : Path
        The ACT4 ELF.
    out_dir : Path
        Where the files are written.
    name : str
        Stem of the file names.
    sdram_base : int
        First address of the SDRAM.

    Returns
    -------
    dict of {str: Path}
        The hex files, under the keys `boot_hex_path` and
        `sdram_hex_path`; `hex_path` is the boot image too, for the
        flash that the platform still has and nobody reads.
    """
    segments = load_segments(elf)
    sdram = region_image(segments, sdram_base, _ADDRESS_SPACE)
    boot = b"".join(
        word.to_bytes(4, "little") for word in sdram_boot_words(sdram_base)
    )
    paths: dict[str, Path] = {}
    for key, suffix, image in (
        ("boot_hex_path", "boot", boot),
        ("sdram_hex_path", "sdram", sdram),
    ):
        bin_path = out_dir / f"{name}.{suffix}.bin"
        hex_path = out_dir / f"{name}.{suffix}.hex"
        bin_path.write_bytes(image or bytes(4))
        bin_to_image.bin_to_hex(bin_path, hex_path)
        paths[key] = hex_path
    paths["hex_path"] = paths["boot_hex_path"]
    return paths


def _raise_stack_limit() -> None:
    """Raise the soft stack limit of this process to the hard one.

    The simulation memories of the ACT4 target are big arrays (millions
    of words), and GHDL allocates them on the stack of the simulation;
    with the default limit it ends with exit code 255 and no message.
    The simulation processes inherit the limit.
    """
    _soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


def _write_elf_images(
    act_cfg: dict[str, Any], elf: Path, test_build_dir: Path
) -> dict[str, Path]:
    """Write the images of one ELF for the platform the config picks.

    Parameters
    ----------
    act_cfg : dict of {str: Any}
        The `act` section of the config.
    elf : Path
        The ELF to convert.
    test_build_dir : Path
        Where the images go.

    Returns
    -------
    dict of {str: Path}
        The image paths, keyed as `write_images` or
        `write_sdram_images` keys them.
    """
    if act_cfg.get("sdram_base") is not None:
        return write_sdram_images(
            elf,
            test_build_dir,
            elf.stem,
            sdram_base=int(str(act_cfg["sdram_base"]), 0),
        )
    return write_images(
        elf,
        test_build_dir,
        elf.stem,
        ram_base=int(str(act_cfg["ram_base"]), 0),
        boot_bytes=int(str(act_cfg["boot_rom_bytes"]), 0),
    )


def _run_elf(
    cfg: dict[str, Any],
    elf: Path,
    test_build_dir: Path,
    vhdl_sources: list[str],
    parameter_templates: dict[str, Any],
) -> bool:
    """Convert one ELF to images and run it under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config.
    elf : Path
        The ELF to run.
    test_build_dir : Path
        The per-ELF build directory.
    vhdl_sources : list of str
        The VHDL sources, already resolved against the root.
    parameter_templates : dict of {str: Any}
        The simulation generics, strings formatted with image paths.

    Returns
    -------
    bool
        Whether the ELF passed.
    """
    act_cfg = cfg["act"]
    images = _write_elf_images(act_cfg, elf, test_build_dir)
    parameters: dict[str, Any] = {
        k: v.format(
            **{key: str(path.resolve()) for key, path in images.items()}
        )
        if isinstance(v, str)
        else v
        for k, v in parameter_templates.items()
    }
    sdram = act_cfg.get("sdram_base") is not None
    return sim_runner.run_test(
        toplevel=cfg["sim"]["toplevel"],
        vhdl_sources=vhdl_sources,
        ghdl_std=cfg["sim"]["ghdl_std"],
        test_module=_ACT_SDRAM_TEST_MODULE if sdram else _ACT_TEST_MODULE,
        hex_path=images["hex_path"],
        test_name=elf.stem,
        build_dir=test_build_dir / "sim_work",
        parameters=parameters,
        # the memories are big arrays, which GHDL refuses to put on
        # the stack by default
        ghdl_run_flags=["--max-stack-alloc=0"],
    )


def run_suite(
    cfg: dict[str, Any], root: Path, build_dir: Path
) -> dict[str, bool]:
    """Build then run every ACT4 ELF of this target under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses its act and sim sections.
    root : Path
        The project root; act.vendor_dir, act.target_config and
        sim.vhdl_sources resolve there.
    build_dir : Path
        Where the converted images and the per-ELF GHDL artifacts go.

    Returns
    -------
    dict of {str: bool}
        {elf stem: passed}, in sorted order.
    """
    _raise_stack_limit()
    sim_runner.extend_python_path(
        root, [".", *(cfg["sim"].get("python_path") or [])]
    )
    act_cfg = cfg["act"]
    vendor_dir = root / act_cfg["vendor_dir"]
    target_config = root / act_cfg["target_config"]

    elfs_dir = build_elfs(
        vendor_dir, target_config, act_cfg["extensions"], act_cfg["jobs"]
    )
    elfs = discover_elfs(elfs_dir)
    if not elfs:
        print(f"No ELFs found under {elfs_dir}; nothing to run")
        return {}

    vhdl_sources = [str(root / src) for src in cfg["sim"]["vhdl_sources"]]
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
        results[name] = _run_elf(
            cfg, elf, test_build_dir, vhdl_sources, parameter_templates
        )
        print(f"{name}: {'PASS' if results[name] else 'FAIL'}")

    return results
