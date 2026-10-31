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
from pathlib import Path
from typing import Any

import yaml

from riscv_tools import proc, sim_runner
from riscv_tools.certify.images import write_images, write_sdram_images

_ACT_TEST_MODULE = "tools.riscv_build.act.sim.test_act"


_ACT_SDRAM_TEST_MODULE = "tools.riscv_build.act.sim.test_act_sdram"


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
