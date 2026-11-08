"""Tests for the swap of the default `config_pkg` for the generated."""

from pathlib import Path

from support import check_equal

from riscv_tools.sources import ordered_sources

MOUNTS = ("Common-Components", "Core")
GITMODULES = "".join(
    f'[submodule "{name}"]\n\tpath = {name}\n'
    f"\turl = git@github.com:insper-riscv/{name}.git\n"
    for name in MOUNTS
)
COMMON = (
    "repository: Common-Components\nprovides:\n"
    "  config:\n    sources: [src/config_pkg.vhd]\n"
    "  counter:\n    sources: [src/counter64.vhd]\n"
    "    requires: [config]\n"
)
CORE = (
    "repository: Core\nprovides:\n"
    "  core:\n    sources: [src/core.vhd]\n"
    "    requires: [Common-Components/counter]\n"
)
TOP = (
    "repository: Top\nprovides:\n"
    "  de0_cv_map:\n    sources: [src/de0-cv/config_pkg.vhd]\n"
    "  top:\n    sources: [src/top.vhd]\n"
    "    requires: [Core/core, de0_cv_map]\n"
    "  top_map_first:\n    sources: [src/top.vhd]\n"
    "    requires: [de0_cv_map, Core/core]\n"
)


def _write(path: Path, text: str = "") -> None:
    """Create a file and the folders above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _workspace(root: Path) -> None:
    """Lay out a top that mounts the Common-Components and the Core."""
    _write(root / ".gitmodules", GITMODULES)
    _write(root / "paths.yaml", TOP)
    _write(root / "Common-Components/paths.yaml", COMMON)
    _write(root / "Core/paths.yaml", CORE)


def test_the_generated_config_pkg_takes_the_place_of_the_default(
    tmp_path: Path,
) -> None:
    """One generated `config_pkg.vhd`, before the units that use it."""
    _workspace(tmp_path)
    check_equal(
        ordered_sources(tmp_path, ["top"]),
        [
            "src/de0-cv/config_pkg.vhd",
            "Common-Components/src/counter64.vhd",
            "Core/src/core.vhd",
            "src/top.vhd",
        ],
    )


def test_the_generated_one_wins_when_it_is_listed_first(
    tmp_path: Path,
) -> None:
    """The default that arrives later never takes the slot."""
    _workspace(tmp_path)
    check_equal(
        ordered_sources(tmp_path, ["top_map_first"]),
        [
            "src/de0-cv/config_pkg.vhd",
            "Common-Components/src/counter64.vhd",
            "Core/src/core.vhd",
            "src/top.vhd",
        ],
    )


def test_without_a_generated_one_the_default_stays(tmp_path: Path) -> None:
    """A target with no generated package keeps the default."""
    _workspace(tmp_path)
    check_equal(
        ordered_sources(tmp_path, ["Core/core"]),
        [
            "Common-Components/src/config_pkg.vhd",
            "Common-Components/src/counter64.vhd",
            "Core/src/core.vhd",
        ],
    )
