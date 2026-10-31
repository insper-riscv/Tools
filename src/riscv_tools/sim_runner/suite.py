"""Run a whole manifest under cocotb/GHDL."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, Unpack

from riscv_tools.sim_runner.core import run_test
from riscv_tools.sim_runner.libraries import (
    build_libraries,
    expand_env,
    extend_python_path,
)

_READABLE_NAME_LIMIT = 48


def _profile_build_dir(build_dir: Path, sim_cfg: dict[str, Any]) -> Path:
    """Return a stable, path-safe work directory for one profile."""
    toplevel = str(sim_cfg["toplevel"])
    readable = re.sub(r"[^A-Za-z0-9_.-]+", "-", toplevel).strip("._-")
    readable = (readable or "toplevel")[:_READABLE_NAME_LIMIT]
    identity = json.dumps(
        sim_cfg, sort_keys=True, separators=(",", ":"), default=str
    )
    fingerprint = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return build_dir / f"{readable}-{fingerprint}"


class BootRomImages(TypedDict, total=False):
    """The optional boot ROM images that `run_suite` passes on."""

    boot_rom_hex_path: Path | None
    boot_rom_mif_path: Path | None


def _resolved(path: Path | None) -> str:
    """Return a path as an absolute string, or "" when it is None."""
    return str(path.resolve()) if path else ""


@dataclass(frozen=True)
class _Suite:
    """What every test of a suite shares, resolved once."""

    cfg: dict[str, Any]
    root: Path
    profile_build_dir: Path
    vhdl_sources: list[str]
    libraries_dir: Path | None
    boot_roms: BootRomImages

    def run_entry(self, entry: dict[str, Any]) -> bool:
        """Run one manifest test under cocotb/GHDL.

        Parameters
        ----------
        entry : dict of {str: Any}
            A manifest entry.

        Returns
        -------
        bool
            Whether the test passed.
        """
        sim_cfg = self.sim_cfg
        name = str(entry["name"])
        print(f"\n=== {name} ({entry['march']}) ===")
        image_key = "mif" if sim_cfg["image"] == "mif" else "hex"
        image_path = self.root / entry[image_key]
        # Lets a project's own sim.parameters, sim.run_files and
        # sim.env reference this test's compiled image (e.g. a VHDL
        # generic that loads the ROM image by path, see
        # sim_runner.__config__) without hardcoding one. The boot ROM
        # paths are the SAME for every entry (built once by the
        # caller); still routed through .format() per test so a
        # project's config can reference them exactly like the test's
        # own image, e.g. `BOOT_ROM_FILE: "{boot_rom_hex_path}"`.
        names = {
            "hex_path": _resolved(image_path) if image_key == "hex" else "",
            "mif_path": _resolved(image_path) if image_key == "mif" else "",
            "boot_rom_hex_path": _resolved(
                self.boot_roms.get("boot_rom_hex_path")
            ),
            "boot_rom_mif_path": _resolved(
                self.boot_roms.get("boot_rom_mif_path")
            ),
        }

        def fill(value: Any) -> Any:
            return value.format(**names) if isinstance(value, str) else value

        templates: dict[str, Any] = sim_cfg.get("parameters") or {}
        golden_path = (
            self.root / entry["golden"] if "golden" in entry else None
        )
        passed = run_test(
            toplevel=sim_cfg["toplevel"],
            vhdl_sources=self.vhdl_sources,
            ghdl_std=sim_cfg["ghdl_std"],
            test_module=sim_cfg["test_module"],
            hex_path=image_path,
            test_name=name,
            build_dir=self.profile_build_dir / name,
            parameters={k: fill(v) for k, v in templates.items()},
            ram_base=self.cfg["memory"]["ram_base"],
            golden_path=golden_path,
            ghdl_flags=list(sim_cfg["ghdl_flags"]),
            libraries_dir=self.libraries_dir,
            run_files={
                file_name: Path(fill(source))
                for file_name, source in sim_cfg["run_files"].items()
            },
            extra_env={k: str(fill(v)) for k, v in sim_cfg["env"].items()},
        )
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
        return passed

    @property
    def sim_cfg(self) -> dict[str, Any]:
        """The `sim` section of the config."""
        return self.cfg["sim"]


def run_suite(
    cfg: dict[str, Any],
    manifest: list[dict[str, Any]],
    root: Path,
    build_dir: Path,
    **boot_roms: Unpack[BootRomImages],
) -> dict[str, bool]:
    """Run every test in manifest under cocotb/GHDL.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config; uses its sim section.
    manifest : list of dict of {str: Any}
        The tests from manifest.json. Each needs "name" and its image
        ("hex", or "mif" when sim.image is "mif"), plus "golden" for a
        "memory"-kind test.
    root : Path
        The project root; entry images and vhdl_sources resolve there.
    build_dir : Path
        Base directory for GHDL artifacts, with one subdirectory per
        simulation profile and one below it per test.
    boot_rom_hex_path : Path, optional
        Compiled .hex of the shared boot ROM, exposed to sim.parameters
        templates as `{boot_rom_hex_path}`.
    boot_rom_mif_path : Path, optional
        The same boot ROM as a .mif (sim.image "mif"), exposed as
        `{boot_rom_mif_path}`.

    Returns
    -------
    dict of {str: bool}
        {test_name: passed}, in manifest order.
    """
    # sim.test_module is a root-relative dotted path (e.g.
    # "tools.riscv_build.sim.test_c_program"): the cocotb subprocess
    # finds it only through the sys.path of this process, also when
    # riscv-tools runs as an installed console script; without it the
    # import fails with "No module named 'tools'".
    sim_cfg = cfg["sim"]
    profile_build_dir = _profile_build_dir(build_dir, sim_cfg)
    extend_python_path(root, [".", *sim_cfg["python_path"]])
    # `root / <absolute path>` is that absolute path, so a variable that
    # expands to one (e.g. Quartus' install directory) is expanded
    # first.
    suite = _Suite(
        cfg=cfg,
        root=root,
        profile_build_dir=profile_build_dir,
        vhdl_sources=[
            str(root / expand_env(src)) for src in sim_cfg["vhdl_sources"]
        ],
        libraries_dir=_build_suite_libraries(sim_cfg, root, profile_build_dir),
        boot_roms=boot_roms,
    )
    return {str(entry["name"]): suite.run_entry(entry) for entry in manifest}


def _build_suite_libraries(
    sim_cfg: dict[str, Any], root: Path, profile_build_dir: Path
) -> Path | None:
    """Analyze the suite's extra VHDL libraries, if it has any.

    Parameters
    ----------
    sim_cfg : dict of {str: Any}
        The `sim` section of the config.
    root : Path
        The project root that library sources are relative to.
    profile_build_dir : Path
        The profile's build directory.

    Returns
    -------
    Path or None
        Where the libraries were analyzed; None when there are none.
    """
    if not sim_cfg["libraries"]:
        return None
    libraries_dir = profile_build_dir / "libraries"
    build_libraries(
        {
            name: [str(root / expand_env(src)) for src in files]
            for name, files in sim_cfg["libraries"].items()
        },
        sim_cfg["ghdl_std"],
        list(sim_cfg["ghdl_flags"]),
        libraries_dir,
    )
    return libraries_dir
