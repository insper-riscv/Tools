"""Build and run the ACT4 architectural certification suite under cocotb/GHDL.

Two stages, kept separate since they're owned by different tools:

1. `build_elfs` shells out to ACT4's own `make` (vendor/riscv-arch-test)
   to compile self-checking ELFs for this project's own ACT4 target
   (act.target_config in config.yaml — see
   tools/riscv_build/act/rv32im-min/). ACT4 owns test generation/
   compilation entirely; this project only supplies the DUT-specific
   config (test_config.yaml, UDB YAML, rvmodel_macros.h, link.ld).
2. `run_suite` converts each built ELF the same way `compiler.build`
   converts this project's own tests (objcopy -> raw .bin ->
   bin_to_image.bin_to_hex), then drives it through the SAME
   cocotb/GHDL toplevel `sim_runner.run_test` uses for the regular
   suite — only `test_module` differs (tools.riscv_build.act.sim.test_act
   instead of the project's own mailbox-watching module), since ACT4
   tests signal completion via HTIF tohost, not this project's own
   PASS/FAIL mailbox convention (see rv32im-min/rvmodel_macros.h).

Doesn't touch real hardware at all — ACT4 tests have no golden.json/
Spike-comparison step of their own (self-checking: the expected value
is baked into each test's own assembly at generation time, upstream,
long before this project ever sees it), so there's nothing here
analogous to orchestrator.run_suite's real-hardware path.
"""

import subprocess
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


def run_suite(cfg: dict[str, Any], root: Path, build_dir: Path) -> dict[str, bool]:
    """Build then run every ACT4 ELF for this project's own target under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config — uses act.vendor_dir/target_config/
        extensions/jobs and sim.toplevel/vhdl_sources/ghdl_std/
        parameters/(NOT sim.test_module — see module docstring) and
        toolchain.objcopy.
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
    parameter_templates: dict[str, Any] = cfg["sim"].get("parameters") or {}

    results: dict[str, bool] = {}
    for elf in elfs:
        name = elf.stem
        print(f"\n=== {name} ===")
        test_build_dir = build_dir / name
        test_build_dir.mkdir(parents=True, exist_ok=True)

        bin_path = test_build_dir / f"{name}.bin"
        hex_path = test_build_dir / f"{name}.hex"
        subprocess.run(
            [str(cfg["toolchain"]["objcopy"]), "-O", "binary", str(elf), str(bin_path)],
            check=True,
        )
        bin_to_image.bin_to_hex(bin_path, hex_path)

        parameters: dict[str, Any] = {
            k: v.format(hex_path=str(hex_path.resolve())) if isinstance(v, str) else v
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
        )
        print(f"{name}: {'PASS' if results[name] else 'FAIL'}")

    return results
